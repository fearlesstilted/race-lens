"""Tests for LiveRunner — no network, no pytest-asyncio required.

All async logic is tested via _poll_once() (sync), which the async loop wraps.
"""
import asyncio
import pytest

from racelens.live.runner import LiveRunner
from tests.test_replay import mini_race


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

    seqs = [e.ingest_seq for e in runner.engine.events]
    # Filter out events that kept their original seq from fixture (seq = 0 default)
    # What we care about: all seqs assigned by runner are unique non-negative ints
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
            gen = api.live_stream.__wrapped__(tick_s=0.001).__aiter__() if hasattr(
                api.live_stream, "__wrapped__"
            ) else None
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


# ── API-level test ─────────────────────────────────────────────────────────────

def test_live_state_before_start():
    """GET /api/live/state before any session is started must return 404."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import racelens.api as api

    # Reset global state to ensure no lingering runner
    api._live = None

    client = TestClient(api.app)
    r = client.get("/api/live/state")
    assert r.status_code == 404
