"""LiveRunner — polling loop that feeds the replay engine.

Architectural invariant (by design):
    The engine is NEVER mutated between polls.  Each poll rebuilds it from
    scratch using ALL accumulated events.  init(5 k events) ≈ 3 ms → negligible.
    This gives us deduplication and determinism for free.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from racelens.events.models import Event
from racelens.replay.engine import ReplayEngine


class LiveRunner:
    """Polls *fetch_events* on a fixed interval and keeps a live ReplayEngine.

    Parameters
    ----------
    fetch_events:
        Callable ``() -> list[Event]`` that returns the **full session snapshot**
        seen so far.  In production this is
        ``lambda: ingest_openf1(session_key)``; in tests a fake.
    poll_interval_s:
        Seconds between polls (default 5.0).
    """

    def __init__(
        self,
        fetch_events: Callable[[], list[Event]],
        poll_interval_s: float = 5.0,
    ) -> None:
        self._fetch = fetch_events
        self._interval = poll_interval_s

        # Accumulated events: event_id → Event
        self._all: dict[str, Event] = {}
        self._seen: set[str] = set()   # same keys as _all, kept separate for O(1) check
        self._next_seq: int = 0        # monotonic ingest_seq counter across polls

        # Stats
        self._polls: int = 0
        self._new_last_poll: int = 0
        self._consecutive_failures: int = 0
        self._last_poll_unix: float | None = None

        # Engine (None until first successful poll)
        self.engine: ReplayEngine | None = None

        # Asyncio task handle
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ── Public interface ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch the background polling loop."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Cancel the background polling loop."""
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def polls(self) -> int:
        return self._polls

    def status(self) -> dict[str, Any]:
        if self._consecutive_failures >= 5:
            dq = "stalled"
        elif self._consecutive_failures >= 2:
            dq = "degraded"
        else:
            dq = "good"
        return {
            "polls": self._polls,
            "events_total": len(self._all),
            "new_last_poll": self._new_last_poll,
            "consecutive_failures": self._consecutive_failures,
            "last_poll_unix": self._last_poll_unix,
            "data_quality": dq,
        }

    def state_now(self) -> dict[str, Any]:
        """Return engine state at the latest known session time."""
        if self.engine is None or not self.engine.events:
            return {"error": "no data yet", "status": self.status()}
        at_ms = self.engine.events[-1].session_time_ms
        state = self.engine.state_at(at_ms)
        state["live_status"] = self.status()
        return state

    # ── Core poll logic (sync, extracted for testability) ────────────────────

    def _poll_once(self) -> None:
        """Execute one poll cycle synchronously.  Errors increment failure counter."""
        try:
            events = self._fetch()
        except Exception:
            self._consecutive_failures += 1
            self._polls += 1
            self._last_poll_unix = time.time()
            self._new_last_poll = 0
            return

        new_count = 0
        for e in events:
            if e.event_id not in self._seen:
                self._seen.add(e.event_id)
                e.ingest_seq = self._next_seq
                self._next_seq += 1
                self._all[e.event_id] = e
                new_count += 1

        if self._all:
            self.engine = ReplayEngine(self._all.values())

        self._consecutive_failures = 0
        self._new_last_poll = new_count
        self._polls += 1
        self._last_poll_unix = time.time()

    # ── Async loop ────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            await asyncio.to_thread(self._poll_once)
            await asyncio.sleep(self._interval)
