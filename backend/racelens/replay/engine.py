"""Deterministic replay engine.

Core guarantee (PLAN.md §10.5):

    same events + same timestamp = same state

The engine never looks past `at_ms` — this is what makes spoiler-free mode
possible at the API layer: serve state_at(t) and nothing else.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from racelens.events.models import Event


def _new_driver() -> dict[str, Any]:
    return {
        "position": None,
        "laps_completed": 0,
        "last_lap_ms": None,
        "best_lap_ms": None,
        "gap_s": None,        # to leader
        "interval_s": None,   # to car ahead
        "tyre_compound": None,
        "tyre_age_laps": None,
        "pit_count": 0,
        "in_pit": False,
    }


class ReplayEngine:
    """Holds a session's normalized events; answers `state_at(t)` queries.

    Events are deduped by event_id and sorted by (session_time_ms, event_id).
    The sort key includes event_id so simultaneous events apply in a stable
    order regardless of input order.
    """

    def __init__(self, events: Iterable[Event]):
        seen: set[str] = set()
        unique: list[Event] = []
        duplicates = 0
        for e in events:
            if e.event_id in seen:
                duplicates += 1
                continue
            seen.add(e.event_id)
            unique.append(e)
        self.events = sorted(unique, key=lambda e: (e.session_time_ms, e.event_id))
        self.duplicates_dropped = duplicates
        self.session_id = self.events[0].session_id if self.events else None

    # ── State construction ────────────────────────────────────────────────

    def state_at(self, at_ms: int) -> dict[str, Any]:
        state: dict[str, Any] = {
            "session_id": self.session_id,
            "at_ms": at_ms,
            "lap": 0,
            "session_status": "unknown",
            "total_laps": None,
            "classification": [],
            "drivers": {},
            "data_quality": {
                "status": "unknown",
                "last_event_ms": None,
                "events_applied": 0,
                "duplicates_dropped": self.duplicates_dropped,
            },
        }

        applied = 0
        last_ms = None
        for e in self.events:
            if e.session_time_ms > at_ms:
                break
            self._apply(state, e)
            applied += 1
            last_ms = e.session_time_ms

        dq = state["data_quality"]
        dq["events_applied"] = applied
        dq["last_event_ms"] = last_ms
        if last_ms is None:
            dq["status"] = "unknown"
        elif at_ms - last_ms > 120_000:
            dq["status"] = "stale"
        else:
            dq["status"] = "good"

        state["classification"] = sorted(
            (d for d, s in state["drivers"].items() if s["position"] is not None),
            key=lambda d: state["drivers"][d]["position"],
        )
        return state

    def state_hash(self, at_ms: int) -> str:
        """Canonical hash of the state — used by determinism tests."""
        blob = json.dumps(self.state_at(at_ms), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ── Event application ─────────────────────────────────────────────────

    def _driver(self, state: dict, driver_id: str) -> dict[str, Any]:
        return state["drivers"].setdefault(driver_id, _new_driver())

    def _apply(self, state: dict, e: Event) -> None:
        p = e.payload

        if e.type == "SessionStarted":
            state["session_status"] = "started"
            state["total_laps"] = p.get("total_laps")

        elif e.type == "SessionStatusChanged":
            state["session_status"] = p.get("status", state["session_status"])

        elif e.type == "LapCompleted":
            d = self._driver(state, e.driver_id)
            d["laps_completed"] = max(d["laps_completed"], e.lap or 0)
            lap_ms = p.get("lap_time_ms")
            if lap_ms is not None:
                d["last_lap_ms"] = lap_ms
                if d["best_lap_ms"] is None or lap_ms < d["best_lap_ms"]:
                    d["best_lap_ms"] = lap_ms
            if d["tyre_age_laps"] is not None:
                d["tyre_age_laps"] += 1
            state["lap"] = max(state["lap"], e.lap or 0)

        elif e.type == "PositionChanged":
            self._driver(state, e.driver_id)["position"] = p.get("position")

        elif e.type == "GapUpdated":
            self._driver(state, e.driver_id)["gap_s"] = p.get("gap_s")

        elif e.type == "IntervalUpdated":
            self._driver(state, e.driver_id)["interval_s"] = p.get("interval_s")

        elif e.type == "PitIn":
            d = self._driver(state, e.driver_id)
            d["in_pit"] = True
            d["pit_count"] += 1

        elif e.type == "PitOut":
            self._driver(state, e.driver_id)["in_pit"] = False

        elif e.type == "TyreStintUpdated":
            d = self._driver(state, e.driver_id)
            d["tyre_compound"] = p.get("compound")
            d["tyre_age_laps"] = p.get("age_laps", 0)

        # RaceControlMessage / WeatherUpdated are carried in the timeline but
        # don't mutate MVP state yet — the insight engine will consume them.
