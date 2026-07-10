"""What-if strategy sensitivity experiment.

Compares the pace outlook with a modified driver state to answer:
  - "baseline"    : what does project_order predict for the rest?
  - "pit_now"     : driver pits now (pit_loss + fresh tyre gain) vs. others at baseline.
  - "stay_out"    : driver skips their stop — degradation penalty compounds.

All outputs are deterministic; no ML, no randomness.
"""
from __future__ import annotations

import copy
from typing import Any

from racelens.forecast.projection import project_order
from racelens.forecast.tracks import track_params

# Fresh-tyre pace bonus per lap (ms) — first ~10 laps on new rubber vs. old worn set.
FRESH_TYRE_GAIN_MS_PER_LAP: float = 400.0

# Extra degradation per lap added when "stay_out" (worn-tyre penalty, ms/lap).
STAY_OUT_DEG_PENALTY_MS_PER_LAP: float = 200.0

VALID_SCENARIOS = {"baseline", "pit_now", "stay_out"}


def _laps_remaining(state: dict) -> int:
    """Estimate laps remaining from total_laps and current lap."""
    total: int = state.get("total_laps") or 60
    current_lap: int = state.get("lap") or 0
    remaining = total - current_lap
    return max(1, remaining)


def _project_finish(state: dict, laps_remaining: int) -> list[str]:
    """Project finishing order from *state* using project_order."""
    result = project_order(state, laps_ahead=laps_remaining)
    return result["projected_order"]


def _build_summary(
    driver: str | None,
    baseline_order: list[str],
    scenario_order: list[str],
    scenario: str,
) -> tuple[str, str]:
    """Build short English + Russian summary strings."""
    if not driver:
        # global scenario — describe top movers
        movers = []
        for drv in baseline_order[:5]:
            b_pos = baseline_order.index(drv) + 1 if drv in baseline_order else None
            s_pos = scenario_order.index(drv) + 1 if drv in scenario_order else None
            if b_pos and s_pos and b_pos != s_pos:
                movers.append((drv, b_pos, s_pos))
        if movers:
            d, b, s = movers[0]
            delta = b - s
            sign = f"+{delta}" if delta > 0 else str(delta)
            en = f"Sensitivity moves {d} from P{b} to P{s} ({sign}) · {scenario}"
            ru = f"Сценарий сдвигает {d} с P{b} на P{s} ({sign}) · {scenario}"
        else:
            en = f"No position changes in this sensitivity · {scenario}"
            ru = f"В этом сценарии позиции не меняются · {scenario}"
        return en, ru

    b_pos = (baseline_order.index(driver) + 1) if driver in baseline_order else None
    s_pos = (scenario_order.index(driver) + 1) if driver in scenario_order else None
    if b_pos is None or s_pos is None:
        return f"{driver} not in pace outlook", f"{driver} отсутствует в расчёте темпа"

    delta = b_pos - s_pos  # positive = gained
    sign = f"+{delta}" if delta > 0 else str(delta)
    en = f"Sensitivity moves {driver} from P{b_pos} to P{s_pos} ({sign})"
    ru = f"Сценарий сдвигает {driver} с P{b_pos} на P{s_pos} ({sign})"
    return en, ru


def what_if(
    state: dict,
    session_id: str,
    scenario: str,
    driver: str | None = None,
) -> dict[str, Any]:
    """Compute an uncalibrated what-if sensitivity comparison.

    Parameters
    ----------
    state       : engine state dict (from ReplayEngine.state_at)
    session_id  : used to look up track params (pit_loss_s)
    scenario    : one of VALID_SCENARIOS
    driver      : required for pit_now / stay_out

    Returns
    -------
    {
        "scenario": str,
        "driver": str | None,
        "baseline_order": [driver_id, ...],
        "scenario_order": [driver_id, ...],
        "diff": [{driver, baseline_pos, scenario_pos, delta}, ...],
        "summary_text_en": str,
        "summary_text_ru": str,
        "assumptions": [str],   # notes on approximations made
    }
    """
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"Invalid scenario '{scenario}'. Must be one of {sorted(VALID_SCENARIOS)}")

    if scenario in {"pit_now", "stay_out"} and not driver:
        raise ValueError(f"scenario='{scenario}' requires a driver parameter")

    laps_rem = _laps_remaining(state)
    assumptions: list[str] = []

    # ── baseline ─────────────────────────────────────────────────────────────
    baseline_order = _project_finish(state, laps_rem)

    # ── scenario ─────────────────────────────────────────────────────────────
    if scenario == "baseline":
        scenario_order = baseline_order[:]

    elif scenario == "pit_now":
        params = track_params(session_id)
        pit_loss_s = params["pit_loss_s"]

        mod_state = copy.deepcopy(state)
        drv_info = _get_driver(mod_state, driver)
        if drv_info is None or drv_info.get("retired"):
            raise ValueError(f"Driver '{driver}' not found or retired in state")

        # Apply pit loss: increase gap_s by pit_loss_s (driver drops back)
        current_gap = drv_info.get("gap_s")
        if current_gap is None and drv_info.get("position") != 1:
            raise ValueError(f"Gap data unavailable for '{driver}'")
        current_gap_s = float(current_gap or 0.0)
        drv_info["gap_s"] = current_gap_s + pit_loss_s

        # Fresh tyre: reset tyre_age to 0, add pace bonus by reducing recent_laps_ms
        # We model fresh-tyre gain by subtracting FRESH_TYRE_GAIN_MS_PER_LAP from each
        # recent lap — effectively giving the driver a faster "base pace" for projection.
        drv_info["tyre_age_laps"] = 0
        recent = drv_info.get("recent_laps_ms") or []
        if recent:
            drv_info["recent_laps_ms"] = [max(60_000.0, ms - FRESH_TYRE_GAIN_MS_PER_LAP) for ms in recent]
        elif drv_info.get("last_lap_ms"):
            drv_info["last_lap_ms"] = max(60_000.0, drv_info["last_lap_ms"] - FRESH_TYRE_GAIN_MS_PER_LAP)

        assumptions.append(
            f"pit_loss={pit_loss_s}s applied; fresh-tyre pace bonus={FRESH_TYRE_GAIN_MS_PER_LAP}ms/lap assumed"
        )
        scenario_order = _project_finish(mod_state, laps_rem)

    elif scenario == "stay_out":
        mod_state = copy.deepcopy(state)
        drv_info = _get_driver(mod_state, driver)
        if drv_info is None or drv_info.get("retired"):
            raise ValueError(f"Driver '{driver}' not found or retired in state")

        # Penalty: increase tyre degradation — add STAY_OUT_DEG_PENALTY to recent laps slope
        # by appending a "degraded" extra lap time to recent_laps_ms so the slope rises
        recent = drv_info.get("recent_laps_ms") or []
        last = drv_info.get("last_lap_ms") or (recent[-1] if recent else 80_000.0)
        # Push projected pace slower: append a lap that's penalty slower
        extra_lap = last + STAY_OUT_DEG_PENALTY_MS_PER_LAP * max(1, len(recent))
        drv_info["recent_laps_ms"] = (list(recent) + [extra_lap])[-5:]
        drv_info["last_lap_ms"] = extra_lap

        assumptions.append(
            f"stay_out: tyre degradation penalty +{STAY_OUT_DEG_PENALTY_MS_PER_LAP}ms/lap applied"
        )
        scenario_order = _project_finish(mod_state, laps_rem)

    else:
        scenario_order = baseline_order[:]

    # ── diff ─────────────────────────────────────────────────────────────────
    all_drivers = list(dict.fromkeys(baseline_order + scenario_order))
    diff: list[dict[str, Any]] = []
    for drv in all_drivers:
        b_pos = (baseline_order.index(drv) + 1) if drv in baseline_order else None
        s_pos = (scenario_order.index(drv) + 1) if drv in scenario_order else None
        if b_pos is None or s_pos is None:
            continue
        diff.append({
            "driver": drv,
            "baseline_pos": b_pos,
            "scenario_pos": s_pos,
            "delta": b_pos - s_pos,  # positive = gained
        })
    # Sort by abs(delta) desc so biggest movers come first
    diff.sort(key=lambda x: (-abs(x["delta"]), x["scenario_pos"]))

    en, ru = _build_summary(driver, baseline_order, scenario_order, scenario)

    return {
        "model": "strategy_sensitivity_v1",
        "calibrated": False,
        "scenario": scenario,
        "driver": driver,
        "baseline_order": baseline_order,
        "scenario_order": scenario_order,
        "diff": diff,
        "summary_text_en": en,
        "summary_text_ru": ru,
        "assumptions": assumptions,
    }


def _get_driver(state: dict, driver: str) -> dict | None:
    """Return the mutable driver info dict from state, or None."""
    drivers: dict = state.get("drivers", {})
    return drivers.get(driver)
