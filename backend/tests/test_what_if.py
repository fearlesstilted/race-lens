"""Tests for racelens.forecast.what_if — counterfactual race-finish projection."""
from __future__ import annotations

import pytest
from pathlib import Path

from racelens.forecast.what_if import what_if, VALID_SCENARIOS
from racelens.forecast.projection import project_order
from racelens.events.models import load_jsonl
from racelens.replay.engine import ReplayEngine


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mk_state(
    drivers: dict,
    total_laps: int = 60,
    at_ms: int = 3_600_000,
    session_id: str = "spain_2024_race",
    current_lap: int = 30,
) -> dict:
    active = sorted(
        [d for d, info in drivers.items() if not info.get("retired") and info.get("position") is not None],
        key=lambda d: drivers[d]["position"],
    )
    retired = [d for d in drivers if drivers[d].get("retired")]
    return {
        "session_id": session_id,
        "at_ms": at_ms,
        "lap": current_lap,
        "total_laps": total_laps,
        "classification": active + retired,
        "drivers": {
            d: {
                "position": info.get("position"),
                "gap_s": info.get("gap_s"),
                "interval_s": info.get("interval_s"),
                "last_lap_ms": info.get("last_lap_ms"),
                "recent_laps_ms": info.get("recent_laps_ms", []),
                "tyre_age_laps": info.get("tyre_age_laps", 10),
                "retired": info.get("retired", False),
                "in_pit": info.get("in_pit", False),
                "pit_count": info.get("pit_count", 0),
                "laps_completed": info.get("laps_completed", current_lap),
                "tyre_compound": info.get("tyre_compound", "M"),
            }
            for d, info in drivers.items()
        },
    }


def _simple_state() -> dict:
    """VER P1, NOR P2 (+5s), LEC P3 (+12s), SAI P4 (+20s) — all on medium."""
    return _mk_state({
        "VER": {"position": 1, "gap_s": 0.0,  "interval_s": None, "last_lap_ms": 78_000, "recent_laps_ms": [78_000, 78_100, 78_200], "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 5.0,  "interval_s": 5.0,  "last_lap_ms": 78_400, "recent_laps_ms": [78_200, 78_400, 78_400], "tyre_age_laps": 20},
        "LEC": {"position": 3, "gap_s": 12.0, "interval_s": 7.0,  "last_lap_ms": 79_000, "recent_laps_ms": [78_800, 79_000, 79_200], "tyre_age_laps": 25},
        "SAI": {"position": 4, "gap_s": 20.0, "interval_s": 8.0,  "last_lap_ms": 79_300, "recent_laps_ms": [79_100, 79_300, 79_500], "tyre_age_laps": 28},
    })


# ── Schema / structural tests ─────────────────────────────────────────────────


def test_what_if_baseline_structure():
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "baseline")
    assert result["scenario"] == "baseline"
    assert result["driver"] is None
    assert isinstance(result["baseline_order"], list)
    assert isinstance(result["scenario_order"], list)
    assert isinstance(result["diff"], list)
    assert isinstance(result["summary_text_en"], str)
    assert isinstance(result["summary_text_ru"], str)
    assert isinstance(result["assumptions"], list)


def test_what_if_diff_structure():
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "baseline")
    for entry in result["diff"]:
        assert "driver" in entry
        assert "baseline_pos" in entry
        assert "scenario_pos" in entry
        assert "delta" in entry
        # delta correctness
        assert entry["delta"] == entry["baseline_pos"] - entry["scenario_pos"]


# ── baseline == project_order order ──────────────────────────────────────────


def test_baseline_matches_project_order():
    """baseline_order must equal what project_order returns for the same state."""
    state = _simple_state()
    laps_rem = (state["total_laps"] or 60) - (state["lap"] or 0)
    expected = project_order(state, laps_ahead=max(1, laps_rem))["projected_order"]
    result = what_if(state, "spain_2024_race", "baseline")
    assert result["baseline_order"] == expected


def test_baseline_scenario_order_equals_baseline_order():
    """For baseline scenario, scenario_order == baseline_order."""
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "baseline")
    assert result["scenario_order"] == result["baseline_order"]


# ── pit_now ──────────────────────────────────────────────────────────────────


def test_pit_now_changes_order_for_backmarker():
    """Pitting the last-place driver from P4 with heavy tyre age should move them."""
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "pit_now", driver="SAI")
    # Scenario order is not necessarily identical to baseline (driver moves after pit+fresh)
    # Just ensure structure is correct and LEC/NOR/VER still in scenario_order
    assert "SAI" in result["scenario_order"]
    for drv in ["VER", "NOR", "LEC"]:
        assert drv in result["scenario_order"]


def test_pit_now_driver_with_worn_tyres_may_recover():
    """LEC on worn tyres (25 laps) — pit_now with fresh rubber should improve projected finish."""
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "pit_now", driver="LEC")
    # After pit + fresh tyre, LEC should gain vs baseline (or at worst same)
    # The pit_loss hurts short-term but fresh pace gains over 30 remaining laps
    # We don't assert specific position but ensure delta is computable
    lec_diff = next(d for d in result["diff"] if d["driver"] == "LEC")
    assert isinstance(lec_diff["delta"], int)


def test_pit_now_pit_loss_appears_in_assumptions():
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "pit_now", driver="NOR")
    assert any("pit_loss" in a for a in result["assumptions"])


def test_pit_now_without_driver_raises():
    state = _simple_state()
    with pytest.raises((ValueError, Exception)):
        what_if(state, "spain_2024_race", "pit_now", driver=None)


# ── stay_out ─────────────────────────────────────────────────────────────────


def test_stay_out_worsens_projection_for_worn_driver():
    """LEC on 25-lap worn tyres — stay_out should push projected finish back vs baseline."""
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "stay_out", driver="LEC")
    baseline_lec = result["baseline_order"].index("LEC") + 1
    scenario_lec = result["scenario_order"].index("LEC") + 1
    # stay_out penalty should not improve LEC's position vs baseline
    assert scenario_lec >= baseline_lec


def test_stay_out_without_driver_raises():
    state = _simple_state()
    with pytest.raises((ValueError, Exception)):
        what_if(state, "spain_2024_race", "stay_out", driver=None)


def test_stay_out_deg_in_assumptions():
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "stay_out", driver="NOR")
    assert any("degradation" in a or "stay_out" in a for a in result["assumptions"])


# ── no_safety_car ─────────────────────────────────────────────────────────────


def test_no_safety_car_returns_valid_structure():
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "no_safety_car")
    assert result["scenario"] == "no_safety_car"
    assert isinstance(result["scenario_order"], list)


def test_no_safety_car_has_approximate_assumption():
    state = _simple_state()
    result = what_if(state, "spain_2024_race", "no_safety_car")
    assert any("approximate" in a or "MVP" in a for a in result["assumptions"])


# ── invalid inputs ────────────────────────────────────────────────────────────


def test_invalid_scenario_raises():
    state = _simple_state()
    with pytest.raises(ValueError, match="Invalid scenario"):
        what_if(state, "spain_2024_race", "turbo_boost")


def test_invalid_scenario_valid_set():
    """All entries in VALID_SCENARIOS must not raise."""
    state = _simple_state()
    for scenario in VALID_SCENARIOS - {"pit_now", "stay_out"}:
        result = what_if(state, "spain_2024_race", scenario)
        assert result["scenario"] == scenario


# ── determinism ──────────────────────────────────────────────────────────────


def test_what_if_deterministic():
    state = _simple_state()
    r1 = what_if(state, "spain_2024_race", "pit_now", driver="LEC")
    r2 = what_if(state, "spain_2024_race", "pit_now", driver="LEC")
    assert r1["scenario_order"] == r2["scenario_order"]
    assert r1["baseline_order"] == r2["baseline_order"]


# ── real fixtures ─────────────────────────────────────────────────────────────


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_engine(session_id: str):
    path = FIXTURES_DIR / f"{session_id}.jsonl"
    if not path.is_file():
        pytest.skip(f"fixture {session_id}.jsonl not found")
    return ReplayEngine(load_jsonl(path.read_text(encoding="utf-8")))


def test_what_if_real_spain_baseline_nonempty():
    eng = _load_engine("spain_2024_race")
    state = eng.state_at(3_600_000)
    result = what_if(state, "spain_2024_race", "baseline")
    assert len(result["baseline_order"]) >= 2


def test_what_if_real_spain_pit_now_lec_diff_nonempty():
    """On real Spain data pit_now for LEC should produce non-trivial diff."""
    eng = _load_engine("spain_2024_race")
    state = eng.state_at(3_600_000)
    # Check LEC is in the race at this timestamp
    if "LEC" not in state.get("drivers", {}) or state["drivers"]["LEC"].get("retired"):
        pytest.skip("LEC not active at this timestamp")
    result = what_if(state, "spain_2024_race", "pit_now", driver="LEC")
    # diff should list LEC with some delta (positive or negative)
    assert len(result["diff"]) >= 1
    assert len(result["baseline_order"]) >= 1
    assert len(result["scenario_order"]) >= 1


def test_what_if_real_spain_pit_now_meaningful_summary():
    eng = _load_engine("spain_2024_race")
    state = eng.state_at(3_600_000)
    if "LEC" not in state.get("drivers", {}) or state["drivers"]["LEC"].get("retired"):
        pytest.skip("LEC not active at this timestamp")
    result = what_if(state, "spain_2024_race", "pit_now", driver="LEC")
    # Summary should mention LEC
    assert "LEC" in result["summary_text_en"]
    assert "LEC" in result["summary_text_ru"]


def test_what_if_real_spain_stay_out_lec():
    eng = _load_engine("spain_2024_race")
    state = eng.state_at(3_600_000)
    if "LEC" not in state.get("drivers", {}) or state["drivers"]["LEC"].get("retired"):
        pytest.skip("LEC not active at this timestamp")
    result = what_if(state, "spain_2024_race", "stay_out", driver="LEC")
    assert len(result["scenario_order"]) >= 1
    assert result["scenario"] == "stay_out"
