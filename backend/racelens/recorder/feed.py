"""Identify and isolate one scheduled session in a SignalR recording."""
from __future__ import annotations

import ast
import json
import os
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from racelens.recorder.schedule import ScheduledSession, canonical_alias

FINISHED_STATUSES = {"Ends", "Finished", "Finalised"}


@dataclass(frozen=True, slots=True)
class FeedInspection:
    matched: bool
    finished: bool
    target_line: int | None
    line_count: int


def _row(raw: str) -> tuple[str, dict[str, Any], str] | None:
    try:
        value = ast.literal_eval(raw.strip())
    except (SyntaxError, ValueError):
        return None
    if not isinstance(value, list) or len(value) < 3 or not isinstance(value[0], str):
        return None
    payload = value[1]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    return value[0], payload, str(value[2] or "")


def _name(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in normalized if char.isalnum() or char.isspace())
        .lower()
        .split()
    )


def session_info_matches(payload: dict[str, Any], session: ScheduledSession) -> bool:
    """Fail closed unless round, year, meeting and session kind all agree."""
    meeting = payload.get("Meeting")
    if not isinstance(meeting, dict):
        return False
    try:
        round_number = int(meeting.get("Number"))
    except (TypeError, ValueError):
        return False
    start = str(payload.get("StartDate") or "")
    return (
        round_number == session.round_number
        and start.startswith(str(session.year))
        and canonical_alias(payload.get("Name")) == session.kind
        and _name(meeting.get("Name")) == _name(session.event_name)
    )


def _has_identity(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("Meeting"), dict) and bool(payload.get("Name"))


def inspect_feed(path: Path, session: ScheduledSession) -> FeedInspection:
    """Inspect only statuses after the latest matching SessionInfo marker."""
    if not path.is_file():
        return FeedInspection(False, False, None, 0)
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    parsed = [_row(line) for line in lines]
    target = None
    for index, item in enumerate(parsed):
        if item and item[0] == "SessionInfo" and session_info_matches(item[1], session):
            target = index
            break
    if target is None:
        return FeedInspection(False, False, None, len(lines))

    finished = False
    for item in parsed[target:]:
        if not item:
            continue
        category, payload, _ = item
        if (
            category == "SessionInfo"
            and _has_identity(payload)
            and not session_info_matches(payload, session)
        ):
            break
        if category == "SessionStatus" and payload.get("Status") in FINISHED_STATUSES:
            finished = True
        if category == "SessionInfo" and payload.get("SessionStatus") in FINISHED_STATUSES:
            finished = True
    return FeedInspection(True, finished, target, len(lines))


def isolate_session(source: Path, destination: Path, session: ScheduledSession) -> None:
    """Atomically remove stale keyframes from other meetings/sessions.

    The public endpoint returns the previous session until the next one starts.
    Keep the latest DriverList before the target marker (driver abbreviations are
    season-stable), then only target-session data.
    """
    lines = source.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    parsed = [_row(line) for line in lines]
    inspection = inspect_feed(source, session)
    if not inspection.matched or inspection.target_line is None:
        raise ValueError(f"recording does not contain {session.session_id}")

    target = inspection.target_line
    prefix: list[str] = []
    for index in range(target - 1, -1, -1):
        item = parsed[index]
        if item and item[0] == "DriverList":
            prefix = [lines[index]]
            break
    end = len(lines)
    for index in range(target + 1, len(parsed)):
        item = parsed[index]
        if (
            item
            and item[0] == "SessionInfo"
            and _has_identity(item[1])
            and not session_info_matches(item[1], session)
        ):
            end = index
            break
    kept = prefix + lines[target:end]
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write("\n".join(kept) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, destination)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
