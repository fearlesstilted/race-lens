"""Tests for the Phase 2 forecast layer: projection, pit simulation, overtake probability."""
from __future__ import annotations

from racelens.forecast.projection import project_order
from racelens.forecast.pit_sim import simulate_pit
from racelens.forecast.overtake import overtake_probability


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mk_state(
    drivers: dict,
    total_laps: int = 60,
    at_ms: int = 3_600_000,
    session_id: str = "spain_2024_race",
) -> dict:
    """Build a minimal engine-style state dict for testing.

    drivers: {driver_id: {position, gap_s, interval_s, last_lap_ms, recent_laps_ms,
                           tyre_age_laps, retired, ...}}
    classification list is derived from position order (active drivers only).
    """
    active = sorted(
        [d for d, info in drivers.items() if not info.get("retired") and info.get("position") is not None],
        key=lambda d: drivers[d]["position"],
    )
    retired = [d for d in drivers if drivers[d].get("retired")]
    return {
        "session_id": session_id,
        "at_ms": at_ms,
        "lap": 30,
        "total_laps": total_laps,
        "classification": active + retired,
        "drivers": {
            d: {
                "position": info.get("position"),
                "gap_s": info.get("gap_s"),
                "interval_s": info.get("interval_s"),
                "last_lap_ms": info.get("last_lap_ms"),
                "recent_laps_ms": info.get("recent_laps_ms", []),
                "tyre_age_laps": info.get("tyre_age_laps", 0),
                "retired": info.get("retired", False),
                "in_pit": info.get("in_pit", False),
                "pit_count": info.get("pit_count", 0),
                "laps_completed": info.get("laps_completed", 30),
                "tyre_compound": info.get("tyre_compound", "M"),
            }
            for d, info in drivers.items()
        },
    }


def _simple_state() -> dict:
    """3-driver state: VER leads, NOR P2 (+5s), LEC P3 (+12s)."""
    return _mk_state({
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None,  "last_lap_ms": 78_000, "recent_laps_ms": [78_000, 78_200, 78_400], "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 5.0, "interval_s": 5.0,   "last_lap_ms": 78_500, "recent_laps_ms": [78_300, 78_500, 78_500], "tyre_age_laps": 20},
        "LEC": {"position": 3, "gap_s": 12.0, "interval_s": 7.0,  "last_lap_ms": 79_000, "recent_laps_ms": [78_800, 79_000, 79_200], "tyre_age_laps": 25},
    })


# ── project_order tests ───────────────────────────────────────────────────────


def test_project_order_deterministic():
    state = _simple_state()
    r1 = project_order(state, laps_ahead=10)
    r2 = project_order(state, laps_ahead=10)
    assert r1 == r2


def test_project_order_structure():
    state = _simple_state()
    result = project_order(state, laps_ahead=10)
    assert "projected_order" in result
    assert "projected" in result
    assert result["laps_ahead"] == 10
    assert result["at_ms"] == state["at_ms"]


def test_project_order_leader_has_zero_gap():
    state = _simple_state()
    result = project_order(state, laps_ahead=10)
    leader = result["projected_order"][0]
    assert result["projected"][leader]["projected_gap_s"] == 0.0


def test_project_order_all_gaps_non_negative():
    state = _simple_state()
    result = project_order(state, laps_ahead=10)
    for driver_id, info in result["projected"].items():
        assert info["projected_gap_s"] >= 0.0, f"{driver_id} has negative gap"


def test_project_order_delta_pos_correct():
    """delta_pos = current_pos - projected_pos; positive = gained positions."""
    state = _simple_state()
    result = project_order(state, laps_ahead=10)
    for driver_id, info in result["projected"].items():
        expected_delta = info["current_pos"] - info["projected_pos"]
        assert info["delta_pos"] == expected_delta


def test_project_order_skips_retired():
    state = _mk_state({
        "VER": {"position": 1, "gap_s": 0.0, "last_lap_ms": 78_000, "recent_laps_ms": [78_000, 78_000]},
        "RET": {"position": None, "gap_s": 50.0, "last_lap_ms": 85_000, "recent_laps_ms": [85_000, 85_000], "retired": True},
    })
    result = project_order(state, laps_ahead=5)
    assert "RET" not in result["projected"]


def test_project_order_preserves_current_place_without_lap_data():
    state = _mk_state({
        "VER": {"position": 1, "gap_s": 0.0, "last_lap_ms": 78_000, "recent_laps_ms": [78_000, 78_000]},
        "NEW": {"position": 2, "gap_s": 5.0, "last_lap_ms": None, "recent_laps_ms": []},
    })
    result = project_order(state, laps_ahead=5)
    # Unknown pace must not make a classified driver disappear.
    assert "VER" in result["projected"]
    assert result["projected_order"] == ["VER", "NEW"]
    assert result["projected"]["NEW"]["projected_gap_s"] is None


def test_project_order_empty_state():
    state = _mk_state({})
    result = project_order(state, laps_ahead=10)
    assert result["projected_order"] == []
    assert result["projected"] == {}


def test_project_order_fallback_to_last_lap_ms():
    """Driver with only last_lap_ms (no recent_laps_ms list) should be projected."""
    state = _mk_state({
        "VER": {"position": 1, "gap_s": 0.0, "last_lap_ms": 78_000, "recent_laps_ms": []},
        "NOR": {"position": 2, "gap_s": 5.0, "last_lap_ms": 78_500, "recent_laps_ms": []},
    })
    result = project_order(state, laps_ahead=5)
    assert "VER" in result["projected"]
    assert "NOR" in result["projected"]


# ── simulate_pit tests ────────────────────────────────────────────────────────


def test_simulate_pit_structure():
    state = _simple_state()
    result = simulate_pit(state, "NOR", "spain_2024_race")
    assert result["driver"] == "NOR"
    assert result["confidence"] == "model"
    ev = result["evidence"]
    assert "pit_loss_s" in ev
    assert "rejoin_gap_s" in ev
    assert "rejoin_pos" in ev
    assert "verdict" in ev


def test_simulate_pit_verdict_valid():
    state = _simple_state()
    result = simulate_pit(state, "NOR", "spain_2024_race")
    assert result["evidence"]["verdict"] in {"UNDERCUT_LIKELY", "UNLIKELY", "NO_RIVAL"}


def test_simulate_pit_rejoin_pos_in_range():
    state = _simple_state()
    n_drivers = len([d for d in state["drivers"] if not state["drivers"][d]["retired"]])
    result = simulate_pit(state, "NOR", "spain_2024_race")
    rp = result["evidence"]["rejoin_pos"]
    assert 1 <= rp <= n_drivers


def test_simulate_pit_margin_is_number():
    state = _simple_state()
    result = simulate_pit(state, "NOR", "spain_2024_race")
    ev = result["evidence"]
    if ev["verdict"] in {"UNDERCUT_LIKELY", "UNLIKELY"}:
        assert isinstance(ev["margin_s"], float)


def test_simulate_pit_leader_no_rival():
    """P1 driver has no car ahead — verdict should be NO_RIVAL."""
    state = _simple_state()
    result = simulate_pit(state, "VER", "spain_2024_race")
    assert result["evidence"]["verdict"] == "NO_RIVAL"


def test_simulate_pit_rejoin_gap_equals_current_plus_pit_loss():
    state = _simple_state()
    result = simulate_pit(state, "NOR", "spain_2024_race")
    ev = result["evidence"]
    expected = round(ev["current_gap_s"] + ev["pit_loss_s"], 3)
    assert ev["rejoin_gap_s"] == expected


def test_simulate_pit_retired_driver_returns_error():
    state = _mk_state({
        "VER": {"position": 1, "gap_s": 0.0, "last_lap_ms": 78_000},
        "RET": {"position": None, "gap_s": 50.0, "retired": True},
    })
    result = simulate_pit(state, "RET", "spain_2024_race")
    assert result["error"] == "driver not found or retired"


def test_simulate_pit_missing_gap_is_not_treated_as_leader():
    state = _mk_state({
        "VER": {"position": 1, "gap_s": 0.0, "last_lap_ms": 78_000},
        "NOR": {"position": 2, "gap_s": None, "last_lap_ms": 78_100},
    })
    result = simulate_pit(state, "NOR", "spain_2024_race")
    assert result["error"] == "gap data unavailable"


def test_simulate_pit_track_pit_loss_used():
    """Monaco has pit_loss_s=21.0, Austria 19.5 — verify different values."""
    state = _simple_state()
    monaco = simulate_pit(state, "NOR", "monaco_2024_race")
    austria = simulate_pit(state, "NOR", "austria_2024_race")
    assert monaco["evidence"]["pit_loss_s"] == 21.0
    assert austria["evidence"]["pit_loss_s"] == 19.5


# ── overtake_probability tests ────────────────────────────────────────────────


def test_overtake_probability_in_range():
    state = _simple_state()
    result = overtake_probability(state, "VER", "NOR", "spain_2024_race")
    assert 0.0 <= result["probability"] <= 1.0


def test_overtake_probability_structure():
    state = _simple_state()
    result = overtake_probability(state, "VER", "NOR", "spain_2024_race")
    assert result["ahead"] == "VER"
    assert result["behind"] == "NOR"
    assert "factors" in result
    factors = result["factors"]
    for key in ("pace_delta_s", "interval_s", "tyre_age_delta_laps", "overtake_difficulty", "logit"):
        assert key in factors


def test_overtake_closer_interval_higher_prob():
    """Smaller interval → higher overtake probability (all else equal)."""
    base = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": 79_000, "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 1.0, "last_lap_ms": 78_000, "tyre_age_laps": 20},
    }
    close = dict(base)
    close["NOR"] = {**base["NOR"], "interval_s": 0.5}
    far = dict(base)
    far["NOR"] = {**base["NOR"], "interval_s": 3.0}

    r_close = overtake_probability(_mk_state(close), "VER", "NOR", "austria_2024_race")
    r_far = overtake_probability(_mk_state(far), "VER", "NOR", "austria_2024_race")
    assert r_close["probability"] > r_far["probability"]


def test_overtake_faster_behind_higher_prob():
    """Behind car faster than ahead → higher overtake probability."""
    drivers_fast = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": 79_500, "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 0.5, "interval_s": 0.5, "last_lap_ms": 78_000, "tyre_age_laps": 20},
    }
    drivers_slow = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": 78_000, "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 0.5, "interval_s": 0.5, "last_lap_ms": 79_500, "tyre_age_laps": 20},
    }
    r_fast = overtake_probability(_mk_state(drivers_fast), "VER", "NOR", "austria_2024_race")
    r_slow = overtake_probability(_mk_state(drivers_slow), "VER", "NOR", "austria_2024_race")
    assert r_fast["probability"] > r_slow["probability"]


def test_overtake_fresher_tyres_behind_higher_prob():
    """Fresh tyres on attacker (higher tyre_age_delta) → higher probability."""
    base_drivers = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": 79_000, "tyre_age_laps": 30},
        "NOR": {"position": 2, "gap_s": 0.5, "interval_s": 0.5, "last_lap_ms": 78_800},
    }
    fresh = {**base_drivers, "NOR": {**base_drivers["NOR"], "tyre_age_laps": 2}}
    worn  = {**base_drivers, "NOR": {**base_drivers["NOR"], "tyre_age_laps": 28}}

    r_fresh = overtake_probability(_mk_state(fresh), "VER", "NOR", "austria_2024_race")
    r_worn  = overtake_probability(_mk_state(worn),  "VER", "NOR", "austria_2024_race")
    assert r_fresh["probability"] > r_worn["probability"]


def test_overtake_monaco_harder_than_austria():
    """Monaco (difficulty=0.95) → lower probability than Austria (0.30), same inputs.

    Use a moderate pace/interval scenario where neither track saturates at 1.0.
    interval=1.5s is enough to keep logit in a range where difficulty matters.
    """
    # interval=0.3s, pace_delta=0.2s: logit≈ -0.9; track difficulty then determines sign.
    # Monaco: logit≈-3.75 (p≈0.02), Austria: logit≈-1.8 (p≈0.14) — clearly different.
    drivers = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": 79_200, "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 0.3, "interval_s": 0.3, "last_lap_ms": 79_000, "tyre_age_laps": 20},
    }
    r_monaco  = overtake_probability(_mk_state(drivers, session_id="monaco_2024_race"),  "VER", "NOR", "monaco_2024_race")
    r_austria = overtake_probability(_mk_state(drivers, session_id="austria_2024_race"), "VER", "NOR", "austria_2024_race")
    assert r_monaco["probability"] < r_austria["probability"]


def test_overtake_missing_lap_data_no_crash():
    """Missing last_lap_ms → pace_delta defaults to 0.0, no exception."""
    drivers = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": None, "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 1.0, "interval_s": 1.0, "last_lap_ms": None, "tyre_age_laps": 20},
    }
    result = overtake_probability(_mk_state(drivers), "VER", "NOR", "spain_2024_race")
    assert 0.0 <= result["probability"] <= 1.0
    assert result["factors"]["pace_delta_s"] == 0.0


def test_overtake_unknown_session_uses_defaults():
    """Unrecognized session_id falls back to default overtake_difficulty=0.60."""
    drivers = {
        "VER": {"position": 1, "gap_s": 0.0, "interval_s": None, "last_lap_ms": 79_000, "tyre_age_laps": 20},
        "NOR": {"position": 2, "gap_s": 0.5, "interval_s": 0.5, "last_lap_ms": 78_000, "tyre_age_laps": 20},
    }
    result = overtake_probability(_mk_state(drivers), "VER", "NOR", "unknown_circuit_2099_race")
    assert result["factors"]["overtake_difficulty"] == 0.60


# ── track_params tests ────────────────────────────────────────────────────────


def test_track_params_prefix_match():
    from racelens.forecast.tracks import track_params
    p = track_params("spain_2024_race")
    assert p["pit_loss_s"] == 21.0
    assert p["overtake_difficulty"] == 0.55


def test_track_params_matches_internal_session_order():
    from racelens.forecast.tracks import track_params
    assert track_params("2024_spain_r")["overtake_difficulty"] == 0.55


def test_track_params_fallback():
    from racelens.forecast.tracks import track_params
    p = track_params("unknown_venue_2099_race")
    assert p["pit_loss_s"] == 21.0
    assert p["overtake_difficulty"] == 0.60


def test_track_params_case_insensitive():
    from racelens.forecast.tracks import track_params
    p1 = track_params("MONACO_2024_RACE")
    p2 = track_params("monaco_2024_race")
    assert p1 == p2
