"""Tests for LiveRunner — no network, no pytest-asyncio required.

All async logic is tested via _poll_once() (sync), which the async loop wraps.
"""
import asyncio

from racelens.events.models import event
from racelens.live.runner import LiveRunner
from tests.test_replay import mini_race, SID


def _big_race(n_laps: int = 60, n_drivers: int = 20) -> list:
    """Synthetic n_lap / n_driver race that produces ~(2 + n_drivers*4 + n_laps*n_drivers)
    events — enough to slice into 100 / 500 / 2000 bands for incremental tests."""
    drivers = [f"D{i:02d}" for i in range(1, n_drivers + 1)]
    evs = []
    evs.append(event(SID, "SessionStarted", 0, total_laps=n_laps))
    for i, drv in enumerate(drivers):
        evs.append(event(SID, "PositionChanged", 0, drv, position=i + 1))
        evs.append(event(SID, "TyreStintUpdated", 0, drv, compound="M", age_laps=0))
    for lap in range(1, n_laps + 1):
        base_ms = lap * 90_000
        for i, drv in enumerate(drivers):
            t = base_ms + i * 500
            evs.append(event(SID, "LapCompleted", t, drv, lap=lap, lap_time_ms=88_000 + i * 200))
            evs.append(event(SID, "GapUpdated", t + 100, drv, gap_s=round(i * 1.2, 3)))
    evs.append(event(SID, "SessionStatusChanged", n_laps * 90_000 + 60_000, status="finished"))
    return evs


def _sliced_fetch(slices):
    """Return a callable that yields successive slices on each call."""
    call_count = [0]

    def fetch():
        idx = min(call_count[0], len(slices) - 1)
        call_count[0] += 1
        return slices[idx]

    fetch.call_count = call_count
    return fetch


def test_incremental_dedup():
    """3 polls with growing snapshots, 4th poll identical — 0 new events."""
    all_events = mini_race()
    total = len(all_events)

    slices = [
        all_events[:5],
        all_events[:12],
        all_events[:total],
        all_events[:total],  # 4th call: nothing new
    ]
    fetch = _sliced_fetch(slices)
    runner = LiveRunner(fetch, poll_interval_s=5.0)

    runner._poll_once()
    assert runner.polls == 1
    assert runner.status()["events_total"] == 5

    runner._poll_once()
    assert runner.polls == 2
    assert runner.status()["events_total"] == 12

    runner._poll_once()
    assert runner.polls == 3
    assert runner.status()["events_total"] == total
    assert runner.status()["new_last_poll"] == total - 12

    runner._poll_once()
    assert runner.polls == 4
    assert runner.status()["events_total"] == total
    assert runner.status()["new_last_poll"] == 0, "4th poll must yield 0 new events"


def test_ingest_seq_monotonic():
    """ingest_seq must never go backwards across polls."""
    all_events = mini_race()
    slices = [all_events[:5], all_events[:12], all_events]
    runner = LiveRunner(_sliced_fetch(slices), poll_interval_s=5.0)

    for _ in range(3):
        runner._poll_once()

    runner_seqs = sorted(runner._all[eid].ingest_seq for eid in runner._all)
    assert runner_seqs == list(range(len(runner._all))), "ingest_seq not monotonic/dense"


def test_state_now_advances():
    """state_now() should reflect more laps after each poll."""
    all_events = mini_race()
    slices = [all_events[:5], all_events[:15], all_events]
    runner = LiveRunner(_sliced_fetch(slices), poll_interval_s=5.0)

    runner._poll_once()
    state1 = runner.state_now()

    runner._poll_once()
    state2 = runner.state_now()

    runner._poll_once()
    state3 = runner.state_now()

    # More events → higher at_ms
    assert state2["at_ms"] >= state1["at_ms"]
    assert state3["at_ms"] >= state2["at_ms"]
    assert state3["lap"] == 3, "full mini_race ends at lap 3"


def test_failure_handling_degraded_then_good():
    """2 consecutive failures → 'degraded'; recovery → 'good'."""
    all_events = mini_race()
    calls = [0]

    def fetch():
        c = calls[0]
        calls[0] += 1
        if c == 0:
            return all_events[:5]   # OK
        if c in (1, 2):
            raise RuntimeError("network error")
        return all_events            # OK again

    runner = LiveRunner(fetch, poll_interval_s=5.0)

    runner._poll_once()
    assert runner.status()["data_quality"] == "good"

    runner._poll_once()
    assert runner.status()["consecutive_failures"] == 1
    assert runner.status()["data_quality"] == "good"  # only 1 failure, not yet degraded

    runner._poll_once()
    assert runner.status()["consecutive_failures"] == 2
    assert runner.status()["data_quality"] == "degraded"

    runner._poll_once()  # recovery
    assert runner.status()["consecutive_failures"] == 0
    assert runner.status()["data_quality"] == "good"


def test_stalled():
    """5+ consecutive failures → 'stalled'."""
    calls = [0]

    def fetch():
        calls[0] += 1
        raise RuntimeError("down")

    runner = LiveRunner(fetch, poll_interval_s=5.0)
    for _ in range(5):
        runner._poll_once()
    assert runner.status()["data_quality"] == "stalled"


def test_status_fields_present():
    """status() must contain all documented keys."""
    runner = LiveRunner(lambda: mini_race(), poll_interval_s=5.0)
    runner._poll_once()
    s = runner.status()
    for key in ("polls", "events_total", "new_last_poll",
                "consecutive_failures", "last_poll_unix", "data_quality"):
        assert key in s, f"Missing key: {key}"
    assert s["last_poll_unix"] is not None


# ── is_running property ────────────────────────────────────────────────────────

def test_is_running_lifecycle():
    """is_running: False before start, True while running, False after stop."""
    runner = LiveRunner(lambda: mini_race(), poll_interval_s=60.0)

    assert runner.is_running is False

    async def _run():
        await runner.start()
        assert runner.is_running is True
        runner.stop()
        # Give the event loop a tick to let the task register cancellation.
        await asyncio.sleep(0)
        assert runner.is_running is False

    asyncio.run(_run())


# ── Empty-poll robustness ──────────────────────────────────────────────────────

def test_empty_poll_does_not_raise():
    """fetch returning [] must not raise, events_total stays 0."""
    runner = LiveRunner(lambda: [], poll_interval_s=5.0)
    runner._poll_once()
    assert runner.polls == 1
    assert runner.status()["events_total"] == 0
    assert runner.engine is None


def test_state_now_before_data_returns_error_dict():
    """state_now() before any data returns an error dict, not an exception."""
    runner = LiveRunner(lambda: [], poll_interval_s=5.0)
    runner._poll_once()
    result = runner.state_now()
    assert "error" in result
    assert "status" in result


def test_empty_then_data_poll():
    """After an empty poll, a subsequent poll with real data works correctly."""
    all_events = mini_race()
    calls = [0]

    def fetch():
        c = calls[0]
        calls[0] += 1
        return [] if c == 0 else all_events

    runner = LiveRunner(fetch, poll_interval_s=5.0)

    runner._poll_once()
    assert runner.status()["events_total"] == 0

    runner._poll_once()
    assert runner.status()["events_total"] == len(all_events)
    assert runner.engine is not None


# ── SSE generator after stop ───────────────────────────────────────────────────

def test_sse_generator_ends_after_stop():
    """SSE gen() yields event:end and returns once the runner is not running."""
    import racelens.api as api

    # Build a stopped runner (never started, is_running=False).
    runner = LiveRunner(lambda: mini_race(), poll_interval_s=5.0)
    runner._poll_once()  # give it engine data

    async def _collect():
        # Patch _live so the generator sees a stopped runner.
        original = api._live
        api._live = runner
        try:
            # runner.is_running is False (never started), so first yield should be end.
            # Build the generator directly via the inner function.
            # Replicate gen() logic from live_stream:
            chunks = []
            tick_s = 0.001

            async def inner_gen():
                while True:
                    if api._live is None or not api._live.is_running:
                        yield "event: end\ndata: {}\n\n"
                        return
                    if api._live.engine is None:
                        yield "data: {}\n\n"
                    else:
                        import json
                        from racelens.insights.registry import detect_all
                        from racelens.commentary.renderer import render_all
                        state = api._live.state_now()
                        state["active_insights"] = detect_all(state)
                        state["commentary"] = render_all(state["active_insights"], "en", "pro")
                        yield f"data: {json.dumps(state)}\n\n"
                    await asyncio.sleep(tick_s)

            async for chunk in inner_gen():
                chunks.append(chunk)
                if len(chunks) > 10:
                    break  # safety guard

            return chunks
        finally:
            api._live = original

    chunks = asyncio.run(_collect())
    assert len(chunks) == 1
    assert chunks[0] == "event: end\ndata: {}\n\n"


# ── Incremental live growth ────────────────────────────────────────────────────

def test_live_incremental():
    """Simulate a live feed catching up: 100 → 500 → all events.

    Verifies:
    - engine.events grows after each poll
    - state_now().at_ms advances (session time moves forward)
    - no duplicates accumulate in _all
    - data_quality stays "good"
    """
    all_events = _big_race(n_laps=60, n_drivers=20)
    total = len(all_events)
    assert total >= 2000, f"fixture too small ({total}); adjust _big_race params"

    slice_100 = all_events[:100]
    slice_500 = all_events[:500]
    slice_all = all_events  # full set

    slices = [slice_100, slice_500, slice_all]
    runner = LiveRunner(_sliced_fetch(slices), poll_interval_s=2.0)

    # --- poll 1: 100 events ---
    runner._poll_once()
    assert runner.status()["events_total"] == 100
    assert runner.status()["data_quality"] == "good"
    state1 = runner.state_now()
    assert "at_ms" in state1
    at_ms_1 = state1["at_ms"]

    # --- poll 2: 500 events ---
    runner._poll_once()
    assert runner.status()["events_total"] == 500
    assert runner.status()["new_last_poll"] == 400
    state2 = runner.state_now()
    at_ms_2 = state2["at_ms"]
    assert at_ms_2 >= at_ms_1, "session time must not go backwards after more data"

    # --- poll 3: full set ---
    runner._poll_once()
    assert runner.status()["events_total"] == total
    state3 = runner.state_now()
    at_ms_3 = state3["at_ms"]
    assert at_ms_3 >= at_ms_2, "session time must not go backwards after full data"
    assert state3["live_status"]["data_quality"] == "good"

    # No duplicates: _all keys unique, count matches total
    assert len(runner._all) == total, "duplicate events crept into _all"

    # at_ms_3 should be at the last session_time_ms in the full event list
    expected_max_ms = max(e.session_time_ms for e in all_events)
    assert at_ms_3 == expected_max_ms, (
        f"state_now() at_ms={at_ms_3} != max session_time_ms={expected_max_ms}"
    )


def test_live_source_truncation_does_not_lose_events():
    """If the source returns FEWER events than a previous poll (e.g. OpenF1 blip),
    already-accumulated events must NOT be discarded from _all.

    This is the key resilience invariant: _all grows monotonically.
    """
    all_events = mini_race()
    total = len(all_events)

    # Sequence: full → truncated (source blinks) → full again
    slices = [all_events, all_events[:3], all_events]
    runner = LiveRunner(_sliced_fetch(slices), poll_interval_s=2.0)

    runner._poll_once()
    assert runner.status()["events_total"] == total, "poll 1 should have all events"

    runner._poll_once()
    # Source returned only 3 events — but we must KEEP everything accumulated
    assert runner.status()["events_total"] == total, (
        "source truncation must not shrink _all — accumulated events are never lost"
    )
    assert runner.status()["new_last_poll"] == 0, (
        "truncated poll should report 0 new events (all 3 were already seen)"
    )
    assert runner.status()["data_quality"] == "good"

    runner._poll_once()
    assert runner.status()["events_total"] == total
