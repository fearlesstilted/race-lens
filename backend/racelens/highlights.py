"""Highlight reel: top-N dramatic moments from a race session."""
from __future__ import annotations
from typing import Any
from racelens.events.models import Event
from racelens.events_significant import significant_events, SEV_CRITICAL, SEV_HIGH, SEV_MEDIUM, SEV_LOW
from racelens.replay.engine import ReplayEngine

_SEV_SCORE = {SEV_CRITICAL: 40, SEV_HIGH: 20, SEV_MEDIUM: 10, SEV_LOW: 4}

# Kind bonus on top of severity
_KIND_BONUS = {
    "LEAD_CHANGE": 15,
    "RED_FLAG": 12,
    "CRASH": 10,
    "SAFETY_CAR": 8,
    "FASTEST_LAP": -6,   # interesting but not dramatic
}

# Dedup window: same kind within this many ms is considered "same moment"
_DEDUP_WINDOW_MS = 30_000


def highlights(
    events: list[Event],
    state_engine: ReplayEngine,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """Return top_n most dramatic moments, sorted chronologically.

    Algorithm:
    1. Get all significant events (full race).
    2. Score each: _SEV_SCORE[severity] + _KIND_BONUS.get(kind, 0).
    3. Dedup: drop events of same kind within _DEDUP_WINDOW_MS of a higher-scored sibling.
    4. Take top_n by score, sort chronologically by at_ms.
    5. Return list of {at_ms, lap, kind, title_en, title_ru, drivers}.
    """
    all_events = significant_events(events, until_ms=None, state_engine=state_engine)
    if not all_events:
        return []

    # Score each event
    scored = []
    for ev in all_events:
        score = _SEV_SCORE.get(ev["severity"], 5) + _KIND_BONUS.get(ev["kind"], 0)
        scored.append((score, ev))

    # Sort by score desc, then at_ms for stability
    scored.sort(key=lambda x: (-x[0], x[1]["at_ms"]))

    # Dedup: greedy — accept highest-scored; skip same-kind within window
    accepted: list[tuple[int, dict[str, Any]]] = []
    for score, ev in scored:
        kind = ev["kind"]
        at_ms = ev["at_ms"]
        too_close = any(
            acc_ev["kind"] == kind and abs(acc_ev["at_ms"] - at_ms) < _DEDUP_WINDOW_MS
            for _, acc_ev in accepted
        )
        if not too_close:
            accepted.append((score, ev))
        if len(accepted) >= top_n:
            break

    # Sort chronologically
    accepted.sort(key=lambda x: x[1]["at_ms"])

    return [
        {
            "at_ms": ev["at_ms"],
            "lap": ev["lap"],
            "kind": ev["kind"],
            "title_en": ev["text_en"],
            "title_ru": ev["text_ru"],
            "drivers": ev["driver_ids"],
        }
        for _, ev in accepted
    ]
