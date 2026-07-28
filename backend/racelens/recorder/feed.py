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
    byte_offset: int = 0
    segment_ended: bool = False


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


def inspect_feed(
    path: Path,
    session: ScheduledSession,
    previous: FeedInspection | None = None,
) -> FeedInspection:
    """Inspect only new append-only rows after a matching SessionInfo marker."""
    if not path.is_file():
        return FeedInspection(False, False, None, 0)
    size = path.stat().st_size
    if previous is None or previous.byte_offset > size:
        previous = FeedInspection(False, False, None, 0)
    if previous.finished or previous.segment_ended or previous.byte_offset == size:
        return previous

    matched = previous.matched
    finished = previous.finished
    target = previous.target_line
    line_count = previous.line_count
    segment_ended = previous.segment_ended
    with path.open("rb") as handle:
        handle.seek(previous.byte_offset)
        for raw in handle:
            item = _row(raw.decode("utf-8-sig", errors="replace"))
            if not raw.endswith(b"\n") and item is None:
                handle.seek(-len(raw), os.SEEK_CUR)
                break
            index = line_count
            line_count += 1
            if not item:
                continue
            category, payload, _ = item
            is_target = category == "SessionInfo" and session_info_matches(payload, session)
            if not matched and is_target:
                matched = True
                target = index
            elif (
                matched
                and category == "SessionInfo"
                and _has_identity(payload)
                and not is_target
            ):
                segment_ended = True
                break
            if matched and (
                category == "SessionStatus" and payload.get("Status") in FINISHED_STATUSES
                or category == "SessionInfo"
                and payload.get("SessionStatus") in FINISHED_STATUSES
            ):
                finished = True
        byte_offset = handle.tell()
    return FeedInspection(
        matched, finished, target, line_count, byte_offset, segment_ended
    )


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
