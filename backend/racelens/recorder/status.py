"""Sanitized recorder status for operators."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from racelens.recorder.state import StateStore


def _age(path: Path, now: datetime) -> float | None:
    if path.is_symlink() or not path.is_file():
        return None
    return round(max(0.0, now.timestamp() - path.stat().st_mtime), 3)


def _publication(directory: Path, session_id: str) -> str:
    state = "none"
    for path in directory.glob("*.ready.*") if directory.is_dir() else ():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("session") != session_id:
                continue
        except (OSError, AttributeError, json.JSONDecodeError):
            continue
        if path.name.endswith(".published"):
            return "published"
        if path.name.endswith(".json"):
            state = "pending"
    return state


def recorder_status(base: Path, now: datetime | None = None) -> dict:
    current = now or datetime.now(UTC)
    state = StateStore(base / "state" / "recorder.json").load()
    latest = max(state.sessions.items(), key=lambda item: item[1].updated_at, default=None)
    heartbeat_age = _age(base / "state" / "heartbeat", current)
    if latest is None:
        return {
            "heartbeat_age_seconds": heartbeat_age,
            "session": None,
            "raw": None,
            "publication": "none",
        }
    session_id, item = latest
    raw = base / "raw" / f"{session_id}.f1live"
    raw_age = _age(raw, current)
    return {
        "heartbeat_age_seconds": heartbeat_age,
        "session": {
            "session_id": session_id,
            "phase": item.phase.value,
            "updated_age_seconds": round(
                max(0.0, (current - item.updated_at).total_seconds()), 3,
            ),
        },
        "raw": {"size_bytes": raw.stat().st_size, "age_seconds": raw_age}
        if raw_age is not None else None,
        "publication": _publication(base / "data" / "publish", session_id),
    }
