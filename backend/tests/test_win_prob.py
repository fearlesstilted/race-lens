"""Tests for racelens.forecast.win_prob."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from racelens.events.models import load_jsonl
from racelens.forecast.win_prob import win_probability
from racelens.replay.engine import ReplayEngine

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_state(
    drivers: dict,
    total_laps: int = 50,
    current_lap: int = 10,
    at_ms: int = 1_000_000,
) -> dict:
    """Build a minimal state dict suitable for win_probability()."""
    return {
        "at_ms": at_ms,
        "lap": current_lap,
        "total_laps": total_laps,
        "classification": list(drivers.keys()),
        "drivers": drivers,
    }


def _driver(
    pos: int,
    gap_s: float = 0.0,
    last_lap_ms: float = 80_000,
    recent_laps_ms: list[float] | None = None,
    retired: bool = False,
) -> dict:
    return {
        "position": pos,
        "gap_s": gap_s,
        "last_lap_ms": last_lap_ms,
        "recent_laps_ms": recent_laps_ms or [last_lap_ms] * 3,
        "laps_completed": 10,
        "retired": retired,
        "in_pit": False,
        "tyre_age_laps": 5,
        "tyre_compound": "MEDIUM",
    }


# ── unit tests ────────────────────────────────────────────────────────────────

def test_probabilities_sum_to_one_basic():
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 5.0),
        "LEC": _driver(3, 12.0),
    })
    result = win_probability(state, "test")
    total = sum(result["win_prob"].values())
    assert abs(total - 1.0) < 1e-6, f"sum={total}"


def test_probabilities_sum_to_one_many_drivers():
    drivers = {
        f"D{i:02d}": _driver(i, gap_s=i * 3.0)
        for i in range(1, 16)
    }
    state = _fake_state(drivers)
    total = sum(win_probability(state, "test")["win_prob"].values())
    assert abs(total - 1.0) < 1e-6


def test_leader_has_highest_probability():
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 8.0),
        "LEC": _driver(3, 20.0),
    })
    probs = win_probability(state, "test")["win_prob"]
    leader_p = probs["VER"]
    assert leader_p == max(probs.values())


def test_late_race_leader_dominates():
    """With only 3 laps left the leader should have P >> 0.5."""
    state = _fake_state(
        {
            "VER": _driver(1, 0.0),
            "NOR": _driver(2, 15.0),
        },
        total_laps=60,
        current_lap=57,
    )
    probs = win_probability(state, "test")
    assert probs["win_prob"]["VER"] > 0.85, probs["win_prob"]


def test_early_race_probabilities_more_spread():
    """Early in the race probabilities should be less concentrated (higher entropy)."""
    drivers = {
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 5.0),
        "LEC": _driver(3, 10.0),
    }
    state_early = _fake_state(drivers, total_laps=60, current_lap=5)
    state_late = _fake_state(drivers, total_laps=60, current_lap=55)

    result_early = win_probability(state_early, "test")
    result_late = win_probability(state_late, "test")

    def entropy(probs: dict) -> float:
        return -sum(p * math.log(p + 1e-12) for p in probs.values())

    e_early = entropy(result_early["win_prob"])
    e_late = entropy(result_late["win_prob"])
    assert e_early > e_late, f"early entropy {e_early:.3f} <= late entropy {e_late:.3f}"


def test_retired_driver_gets_zero():
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 5.0),
        "DNF": _driver(3, 15.0, retired=True),
    })
    result = win_probability(state, "test")
    assert result["win_prob"].get("DNF", 0) == 0.0


def test_remaining_sum_to_one_after_retirement():
    """Non-retired driver probabilities must still sum to 1."""
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 5.0),
        "DNF": _driver(3, 15.0, retired=True),
    })
    probs = win_probability(state, "test")["win_prob"]
    non_zero = {d: p for d, p in probs.items() if p > 0}
    total = sum(non_zero.values())
    assert abs(total - 1.0) < 1e-6, f"non-zero sum={total}"


def test_determinism():
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 7.5),
        "LEC": _driver(3, 18.0),
    })
    r1 = win_probability(state, "test")
    r2 = win_probability(state, "test")
    assert r1 == r2


def test_laps_ahead_override():
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 5.0),
    })
    # With 1 lap left leader should dominate vs. 40 laps left
    r_short = win_probability(state, "test", laps_ahead=1)
    r_long = win_probability(state, "test", laps_ahead=40)
    assert r_short["win_prob"]["VER"] > r_long["win_prob"]["VER"]


def test_top_list_sorted_desc():
    state = _fake_state({
        f"D{i}": _driver(i, gap_s=i * 5.0)
        for i in range(1, 8)
    })
    top = win_probability(state, "test")["top"]
    probs = [t["prob"] for t in top]
    assert probs == sorted(probs, reverse=True)


def test_leader_field():
    state = _fake_state({
        "VER": _driver(1, 0.0),
        "NOR": _driver(2, 5.0),
    })
    result = win_probability(state, "test")
    assert result["leader"] == "VER"


# ── fixture-based sanity tests ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def spain_engine():
    path = FIXTURES / "spain_2024_race.jsonl"
    if not path.exists():
        pytest.skip("spain_2024_race.jsonl not found")
    return ReplayEngine(load_jsonl(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def miami_engine():
    path = FIXTURES / "miami_2026_race.jsonl"
    if not path.exists():
        pytest.skip("miami_2026_race.jsonl not found")
    return ReplayEngine(load_jsonl(path.read_text(encoding="utf-8")))


def test_spain_late_leader_dominates(spain_engine):
    end_ms = spain_engine.events[-1].session_time_ms
    at_ms = int(end_ms * 0.92)
    state = spain_engine.state_at(at_ms)
    result = win_probability(state, "spain_2024_race")
    top = result["top"]
    assert top, "top list is empty"
    leader_prob = top[0]["prob"]
    assert leader_prob > 0.65, f"expected leader p>0.65 late in race, got {leader_prob}"


def test_spain_early_more_uniform(spain_engine):
    end_ms = spain_engine.events[-1].session_time_ms
    at_ms_early = int(end_ms * 0.10)
    at_ms_late = int(end_ms * 0.90)
    state_early = spain_engine.state_at(at_ms_early)
    state_late = spain_engine.state_at(at_ms_late)
    r_early = win_probability(state_early, "spain_2024_race")
    r_late = win_probability(state_late, "spain_2024_race")

    def entropy(probs: dict) -> float:
        return -sum(p * math.log(p + 1e-12) for p in probs.values() if p > 0)

    assert entropy(r_early["win_prob"]) > entropy(r_late["win_prob"])


def test_spain_sums_to_one(spain_engine):
    end_ms = spain_engine.events[-1].session_time_ms
    at_ms = int(end_ms * 0.5)
    state = spain_engine.state_at(at_ms)
    result = win_probability(state, "spain_2024_race")
    non_zero = [p for p in result["win_prob"].values() if p > 0]
    total = sum(non_zero)
    assert abs(total - 1.0) < 1e-5, f"sum={total}"


def test_miami_sums_to_one(miami_engine):
    end_ms = miami_engine.events[-1].session_time_ms
    at_ms = int(end_ms * 0.5)
    state = miami_engine.state_at(at_ms)
    result = win_probability(state, "miami_2026_race")
    non_zero = [p for p in result["win_prob"].values() if p > 0]
    total = sum(non_zero)
    assert abs(total - 1.0) < 1e-5, f"sum={total}"
