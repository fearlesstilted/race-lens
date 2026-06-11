"""Tests for LiveRunner — no network, no pytest-asyncio required.

All async logic is tested via _poll_once() (sync), which the async loop wraps.
"""
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
