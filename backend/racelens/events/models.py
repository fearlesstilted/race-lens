"""Event envelope and event types — the contract everything else builds on.

Every piece of raw motorsport data (FastF1, OpenF1, fixtures) is normalized
into Event before it touches the replay engine. See PLAN.md §10.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, Field

# Raw events — produced by adapters
EVENT_TYPES = {
    "SessionStarted",
    "SessionStatusChanged",
    "LapCompleted",
    "PositionChanged",
    "GapUpdated",
    "IntervalUpdated",
    "PitIn",
    "PitOut",
    "TyreStintUpdated",
    "RaceControlMessage",
    "WeatherUpdated",
}


class Event(BaseModel):
    """Normalized event envelope. Stable ID, ordered by session_time_ms."""

    event_id: str
    session_id: str
    type: str
    session_time_ms: int
    lap: Optional[int] = None
    driver_id: Optional[str] = None
    source: str = "fixture"
    confidence: str = "high"
    # Monotonic arrival order, assigned at ingestion. Replay uses session_time_ms
    # (event time); near-live watermarks use ingest_seq (processing time), so
    # late-arriving events can revise state without breaking determinism.
    ingest_seq: Optional[int] = None
    payload: dict[str, Any] = Field(default_factory=dict)


def make_event_id(
    session_id: str,
    type_: str,
    session_time_ms: int,
    driver_id: Optional[str],
    payload: dict[str, Any],
) -> str:
    """Deterministic event ID: same input data → same ID, across runs and sources.

    This is what makes dedupe and replay determinism possible.
    """
    raw = json.dumps(
        [session_id, type_, session_time_ms, driver_id, payload],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def event(
    session_id: str,
    type_: str,
    session_time_ms: int,
    driver_id: Optional[str] = None,
    lap: Optional[int] = None,
    source: str = "fixture",
    **payload: Any,
) -> Event:
    """Convenience constructor with auto-generated deterministic ID."""
    return Event(
        event_id=make_event_id(session_id, type_, session_time_ms, driver_id, payload),
        session_id=session_id,
        type=type_,
        session_time_ms=session_time_ms,
        driver_id=driver_id,
        lap=lap,
        source=source,
        payload=payload,
    )


def dump_jsonl(events: list[Event]) -> str:
    return "\n".join(e.model_dump_json(exclude_none=True) for e in events) + "\n"


def load_jsonl(text: str) -> list[Event]:
    return [Event.model_validate_json(line) for line in text.splitlines() if line.strip()]
