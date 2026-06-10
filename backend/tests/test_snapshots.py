"""Snapshots are an optimization, not a semantic change: states must be
byte-identical with and without them, at every timestamp."""
from racelens.replay.engine import ReplayEngine

from tests.test_replay import mini_race


def test_snapshot_states_identical_to_full_replay():
    events = mini_race()
    plain = ReplayEngine(events, snapshot_interval=0)       # no snapshots
    dense = ReplayEngine(events, snapshot_interval=3)       # snapshot every 3 events
    for t in range(0, 320_000, 10_000):
        assert dense.state_at(t) == plain.state_at(t)
        assert dense.state_hash(t) == plain.state_hash(t)


def test_snapshot_isolation():
    """Querying must never mutate stored snapshots."""
    engine = ReplayEngine(mini_race(), snapshot_interval=3)
    first = engine.state_at(300_000)
    for t in (0, 140_000, 50_000, 300_000):  # interleaved queries
        engine.state_at(t)
    assert engine.state_at(300_000) == first
