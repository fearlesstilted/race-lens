"""Atomic, corruption-safe recorder state stored as JSON."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

SESSION_ID = re.compile(r"^\d{4}-\d{2}-(?:fp[123]|sq|sprint|q|r)$")


class Phase(str, Enum):
    RECORDING = "recording"
    CAPTURED = "captured"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


_NEXT = {
    None: {Phase.RECORDING},
    Phase.RECORDING: {Phase.CAPTURED, Phase.FAILED},
    Phase.CAPTURED: {Phase.PROCESSING, Phase.FAILED},
    Phase.PROCESSING: {Phase.COMPLETE, Phase.FAILED},
    Phase.FAILED: set(),  # selected from the persisted retry_phase below
    Phase.COMPLETE: set(),
}


class CorruptStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SessionState:
    phase: Phase
    attempts: int
    updated_at: datetime
    last_error: str | None = None
    retry_at: datetime | None = None
    retry_phase: Phase | None = None


@dataclass(frozen=True, slots=True)
class RecorderState:
    sessions: dict[str, SessionState] = field(default_factory=dict)
    version: int = 1

    def due_phase(self, session_id: str, now: datetime) -> Phase | None:
        """Next runnable phase, preserving captured data across processing retries."""
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        current = self.sessions.get(session_id)
        if current is None:
            return Phase.RECORDING
        if current.phase is not Phase.FAILED or current.retry_at is None:
            return None
        return current.retry_phase if now.astimezone(UTC) >= current.retry_at else None

    def can_attempt(self, session_id: str, now: datetime) -> bool:
        return self.due_phase(session_id, now) is not None


def _time(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC)


def _decode(raw: str) -> RecorderState:
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("unsupported recorder state")
    rows = data.get("sessions")
    if not isinstance(rows, dict):
        raise ValueError("sessions must be an object")
    sessions: dict[str, SessionState] = {}
    for session_id, row in rows.items():
        if (
            not isinstance(session_id, str)
            or SESSION_ID.fullmatch(session_id) is None
            or not isinstance(row, dict)
        ):
            raise ValueError("invalid session state")
        attempts = row.get("attempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
            raise ValueError("attempts must be a positive integer")
        updated_at = _time(row.get("updated_at"), "updated_at")
        if updated_at is None:
            raise ValueError("updated_at is required")
        sessions[session_id] = SessionState(
            phase=Phase(row["phase"]),
            attempts=attempts,
            updated_at=updated_at,
            last_error=row.get("last_error"),
            retry_at=_time(row.get("retry_at"), "retry_at"),
            retry_phase=Phase(row["retry_phase"]) if row.get("retry_phase") else None,
        )
        if sessions[session_id].last_error is not None and not isinstance(
            sessions[session_id].last_error, str
        ):
            raise ValueError("last_error must be a string")
        failed = sessions[session_id].phase is Phase.FAILED
        retry_data = (
            sessions[session_id].last_error,
            sessions[session_id].retry_at,
            sessions[session_id].retry_phase,
        )
        if failed:
            if not retry_data[0] or retry_data[1] is None or retry_data[2] not in {
                Phase.RECORDING, Phase.PROCESSING,
            }:
                raise ValueError("failed state requires complete retry metadata")
        elif any(value is not None for value in retry_data):
            raise ValueError("only failed state may have retry metadata")
    return RecorderState(sessions=sessions)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("state timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _encode(state: RecorderState) -> str:
    data: dict[str, Any] = {"version": state.version, "sessions": {}}
    for session_id, item in sorted(state.sessions.items()):
        row = asdict(item)
        row["phase"] = item.phase.value
        row["updated_at"] = _iso(item.updated_at)
        row["retry_at"] = _iso(item.retry_at)
        row["retry_phase"] = item.retry_phase.value if item.retry_phase else None
        data["sessions"][session_id] = row
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> RecorderState:
        if not self.path.exists():
            return RecorderState()
        try:
            return _decode(self.path.read_text(encoding="utf-8"))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise CorruptStateError(f"refusing corrupt recorder state: {self.path}") from exc

    def save(self, state: RecorderState) -> bool:
        """Atomically persist state; return False when no semantic change exists."""
        encoded = _encode(state)
        _decode(encoded)  # refuse to persist a state that we could not read back
        if self.path.exists():
            # Reading first is intentional: corrupt state must never be replaced.
            if self.load() == state:
                return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                tmp_name = handle.name
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
            return True
        finally:
            if tmp_name is not None:
                Path(tmp_name).unlink(missing_ok=True)

    def transition(
        self,
        session_id: str,
        phase: Phase,
        now: datetime,
        *,
        error: str | None = None,
        retry_at: datetime | None = None,
    ) -> RecorderState:
        if now.tzinfo is None or (retry_at is not None and retry_at.tzinfo is None):
            raise ValueError("timestamps must be timezone-aware")
        state = self.load()
        current = state.sessions.get(session_id)
        if current is not None and current.phase is phase:
            return state
        previous_phase = current.phase if current else None
        allowed = _NEXT[previous_phase]
        if previous_phase is Phase.FAILED:
            allowed = {current.retry_phase} if current else set()
        if phase not in allowed:
            raise ValueError(f"invalid transition: {previous_phase} -> {phase}")
        if (
            previous_phase is Phase.FAILED
            and current is not None
            and current.retry_at is not None
            and now.astimezone(UTC) < current.retry_at
        ):
            raise ValueError("retry is not due")
        if phase is Phase.FAILED and (not error or retry_at is None):
            raise ValueError("failed state requires error and retry_at")
        if phase is not Phase.FAILED and (error is not None or retry_at is not None):
            raise ValueError("retry metadata is only valid for failed state")
        attempts = (current.attempts if current else 0) + (phase is Phase.RECORDING)
        retry_phase = None
        if phase is Phase.FAILED:
            retry_phase = (
                Phase.PROCESSING
                if previous_phase in {Phase.CAPTURED, Phase.PROCESSING}
                else Phase.RECORDING
            )
        next_item = SessionState(
            phase=phase,
            attempts=attempts,
            updated_at=now.astimezone(UTC),
            last_error=error,
            retry_at=retry_at.astimezone(UTC) if retry_at else None,
            retry_phase=retry_phase,
        )
        sessions = dict(state.sessions)
        sessions[session_id] = next_item
        updated = RecorderState(sessions=sessions)
        self.save(updated)
        return updated
