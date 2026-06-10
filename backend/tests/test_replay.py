"""Replay engine tests: correctness, determinism, dedupe, no future leakage."""
import random

from racelens.events.models import dump_jsonl, event, load_jsonl
from racelens.replay.engine import ReplayEngine

SID = "2024_mini_race"


def mini_race():
    """Synthetic 3-lap, 3-driver race: VER leads, LEC pits on lap 2 and drops to P3."""
    e = []

    # Grid + start
    e.append(event(SID, "SessionStarted", 0, total_laps=3))
    for drv, pos in [("VER", 1), ("LEC", 2), ("NOR", 3)]:
        e.append(event(SID, "PositionChanged", 0, drv, position=pos))
        e.append(event(SID, "TyreStintUpdated", 0, drv, compound="M", age_laps=0))

    # Lap 1
    e.append(event(SID, "LapCompleted", 80_000, "VER", lap=1, lap_time_ms=78_000))
    e.append(event(SID, "LapCompleted", 81_000, "LEC", lap=1, lap_time_ms=79_000))
    e.append(event(SID, "LapCompleted", 82_000, "NOR", lap=1, lap_time_ms=80_000))
    e.append(event(SID, "GapUpdated", 82_500, "LEC", gap_s=1.0))
    e.append(event(SID, "GapUpdated", 82_500, "NOR", gap_s=2.0))

    # LEC pits during lap 2, rejoins P3 on hards
    e.append(event(SID, "PitIn", 110_000, "LEC", lap=2))
    e.append(event(SID, "PitOut", 135_000, "LEC", lap=2))
    e.append(event(SID, "TyreStintUpdated", 135_000, "LEC", compound="H", age_laps=0))
    e.append(event(SID, "PositionChanged", 136_000, "LEC", position=3))
    e.append(event(SID, "PositionChanged", 136_000, "NOR", position=2))

    # Lap 2
    e.append(event(SID, "LapCompleted", 160_000, "VER", lap=2, lap_time_ms=77_500))
    e.append(event(SID, "LapCompleted", 163_000, "NOR", lap=2, lap_time_ms=80_500))
    e.append(event(SID, "LapCompleted", 168_000, "LEC", lap=2, lap_time_ms=86_000))

    # Lap 3 + finish
    e.append(event(SID, "LapCompleted", 238_000, "VER", lap=3, lap_time_ms=77_900))
    e.append(event(SID, "LapCompleted", 242_000, "NOR", lap=3, lap_time_ms=79_800))
    e.append(event(SID, "LapCompleted", 245_000, "LEC", lap=3, lap_time_ms=77_000))
    e.append(event(SID, "SessionStatusChanged", 250_000, status="finished"))
    return e


def test_state_before_lap_one():
    s = ReplayEngine(mini_race()).state_at(50_000)
    assert s["lap"] == 0
    assert s["session_status"] == "started"
    assert s["classification"] == ["VER", "LEC", "NOR"]
    assert all(d["tyre_compound"] == "M" for d in s["drivers"].values())
    assert s["drivers"]["LEC"]["pit_count"] == 0


def test_state_after_pit_stop():
    s = ReplayEngine(mini_race()).state_at(140_000)
    lec = s["drivers"]["LEC"]
    assert lec["pit_count"] == 1
    assert lec["in_pit"] is False          # out at 135s
    assert lec["tyre_compound"] == "H"
    assert lec["tyre_age_laps"] == 0
    assert s["classification"] == ["VER", "NOR", "LEC"]
    assert s["lap"] == 1                   # nobody finished lap 2 yet


def test_state_at_finish():
    s = ReplayEngine(mini_race()).state_at(300_000)
    assert s["session_status"] == "finished"
    assert s["lap"] == 3
    assert s["drivers"]["VER"]["best_lap_ms"] == 77_500
    assert s["drivers"]["LEC"]["best_lap_ms"] == 77_000  # fastest lap on fresh hards
    assert s["drivers"]["LEC"]["tyre_age_laps"] == 2     # laps 2 and 3 on the H set
    assert s["data_quality"]["status"] == "good"         # 50s past last event, within threshold
    late = ReplayEngine(mini_race()).state_at(400_000)
    assert late["data_quality"]["status"] == "stale"     # 150s silence → stale


def test_determinism_under_shuffle():
    events = mini_race()
    baseline = ReplayEngine(events)
    for seed in (1, 42, 1337):
        shuffled = events[:]
        random.Random(seed).shuffle(shuffled)
        engine = ReplayEngine(shuffled)
        for t in (0, 50_000, 140_000, 300_000):
            assert engine.state_hash(t) == baseline.state_hash(t)


def test_duplicate_events_dropped():
    events = mini_race()
    noisy = events + events[5:12]  # replay a chunk, as a flaky live feed would
    engine = ReplayEngine(noisy)
    clean = ReplayEngine(events)
    assert engine.duplicates_dropped == 7
    s_noisy, s_clean = engine.state_at(300_000), clean.state_at(300_000)
    assert s_noisy["drivers"] == s_clean["drivers"]      # no double-counted pits/laps
    assert s_noisy["classification"] == s_clean["classification"]


def test_no_future_leakage():
    """State at t must be identical whether or not future events exist at all."""
    events = mini_race()
    cutoff = 140_000
    full = ReplayEngine(events)
    truncated = ReplayEngine([e for e in events if e.session_time_ms <= cutoff])
    assert full.state_at(cutoff) == truncated.state_at(cutoff)


def test_jsonl_round_trip():
    events = mini_race()
    restored = load_jsonl(dump_jsonl(events))
    assert restored == events
    assert ReplayEngine(restored).state_hash(300_000) == ReplayEngine(events).state_hash(300_000)
