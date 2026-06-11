"""Tests for detect_clean_air_pace (PLAN.md §12.3)."""
from racelens.insights.clean_air import detect_clean_air_pace
from racelens.replay.engine import ReplayEngine

from tests.test_replay import mini_race


# ── helpers ──────────────────────────────────────────────────────────────────

def _base_state(**overrides):
    """Minimal valid state with one driver in clean air."""
    state = {
        "at_ms": 300_000,
        "lap": 3,
        "session_status": "started",
        "classification": ["VER", "LEC"],
        "drivers": {
            "VER": {
                "interval_s": None,  # race leader
                "in_pit": False,
                "recent_laps_ms": [78_000, 78_200, 78_100],
                "last_lap_ms": 78_100,
            },
            "LEC": {
                "interval_s": 3.0,   # clear air
                "in_pit": False,
                "recent_laps_ms": [77_500, 77_200, 77_300],
                "last_lap_ms": 77_300,
            },
        },
    }
    state.update(overrides)
    return state


# ── actual tests ──────────────────────────────────────────────────────────────

def test_leader_in_clean_air():
    """Race leader always qualifies (interval_s is None)."""
    state = _base_state()
    # Remove LEC so only VER is in clean air
    state["classification"] = ["VER"]
    del state["drivers"]["LEC"]
    result = detect_clean_air_pace(state)
    assert len(result) == 1
    ins = result[0]
    assert ins["type"] == "CLEAN_AIR_PACE_LEADER"
    assert ins["driver_ids"] == ["VER"]
    # VER IS the leader, so vs_race_leader_ms should be 0.0
    assert ins["evidence"]["vs_race_leader_ms"] == 0.0
    assert ins["severity"] == "info"  # not faster than himself


def test_backmarker_faster_than_leader_gives_medium():
    """Fastest clean-air car faster than race leader → severity=medium."""
    state = _base_state()
    # LEC avg = (77500+77200+77300)/3 ≈ 77333, VER avg ≈ 78100
    result = detect_clean_air_pace(state)
    assert len(result) == 1
    ins = result[0]
    assert ins["driver_ids"] == ["LEC"]
    assert ins["severity"] == "medium"
    assert ins["evidence"]["vs_race_leader_ms"] is not None
    assert ins["evidence"]["vs_race_leader_ms"] < 0


def test_all_in_traffic_returns_empty():
    """Everyone within the clean-air threshold → no insight."""
    state = _base_state()
    state["drivers"]["LEC"]["interval_s"] = 0.5   # in traffic
    state["drivers"]["VER"]["interval_s"] = None  # leader — still qualifies
    # VER is the only clean-air driver; LEC is in traffic
    result = detect_clean_air_pace(state)
    assert len(result) == 1
    assert result[0]["driver_ids"] == ["VER"]


def test_fully_in_traffic_returns_empty():
    """If the leader is also in pit, nobody qualifies."""
    state = _base_state()
    state["classification"] = ["VER", "LEC"]
    state["drivers"]["VER"]["in_pit"] = True
    state["drivers"]["LEC"]["interval_s"] = 0.3
    result = detect_clean_air_pace(state)
    assert result == []


def test_safety_car_returns_empty():
    """Under SC/VSC/red flag the insight is suppressed (session_status guard)."""
    state = _base_state()
    state["session_status"] = "safety_car"
    assert detect_clean_air_pace(state) == []


def test_finished_session_returns_empty():
    """session_status != 'started' → []."""
    state = _base_state()
    state["session_status"] = "finished"
    assert detect_clean_air_pace(state) == []


def test_not_enough_recent_laps():
    """Drivers without 3 recent laps are excluded."""
    state = _base_state()
    state["drivers"]["LEC"]["recent_laps_ms"] = [77_300, 77_200]  # only 2
    # VER still qualifies as leader
    result = detect_clean_air_pace(state)
    assert result[0]["driver_ids"] == ["VER"]


def test_drivers_in_clean_air_count():
    """evidence.drivers_in_clean_air reflects true count."""
    state = _base_state()
    result = detect_clean_air_pace(state)
    assert result[0]["evidence"]["drivers_in_clean_air"] == 2


def test_mini_race_at_end():
    """Smoke test on mini_race fixture: at 247s, LEC on fresh hards is clear (interval 0.7 ≤ 2.5 → IN TRAFFIC → not detected)."""
    s = ReplayEngine(mini_race()).state_at(247_000)
    result = detect_clean_air_pace(s)
    # LEC interval_s = 0.7 — within threshold, so LEC not in clean air
    ids = [r["driver_ids"][0] for r in result]
    assert "LEC" not in ids
