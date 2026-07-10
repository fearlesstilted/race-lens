"""Pit stop simulation model.

Estimates where a driver would re-join the race if they pitted NOW, and whether
an undercut on their immediate rival is likely.

Model:
  rejoin_gap_to_leader = current_gap_s + pit_loss_s
  undercut margin      = TYRE_ADVANTAGE_PER_LAP * UNDERCUT_LAPS - (rejoin_gap - rival_gap)
  verdict              = UNDERCUT_LIKELY if margin > 0 else UNLIKELY
"""
from __future__ import annotations

from typing import Any

from racelens.forecast.tracks import track_params

TYRE_ADVANTAGE_PER_LAP_S: float = 0.8   # fresh tyre pace gain vs. worn tyre
UNDERCUT_LAPS: int = 2                   # laps over which undercut plays out


def simulate_pit(state: Any, driver: str, session_id: str) -> dict:
    """Simulate driver pitting right now.

    Returns
    -------
    {
        "driver": str,
        "confidence": "model",
        "evidence": {
            "pit_loss_s": float,
            "current_gap_s": float,
            "rejoin_gap_s": float,
            "rejoin_pos": int,
            "key_rival": str | None,
            "rival_gap_s": float | None,
            "margin_s": float | None,
            "verdict": "UNDERCUT_LIKELY" | "UNLIKELY" | "NO_RIVAL",
        }
    }
    """
    params = track_params(session_id)
    pit_loss_s: float = params["pit_loss_s"]

    # Support both dict (engine output) and object-style state
    if isinstance(state, dict):
        classification_list = state.get("classification", [])
        drivers = state.get("drivers", {})
        cls_dict: dict[str, Any] = {d: drivers[d] for d in classification_list if d in drivers}
    else:
        cls_dict = state.classification or {}

    info = cls_dict.get(driver)
    if info is None or info.get("retired"):
        return {
            "driver": driver,
            "confidence": "unavailable",
            "error": "driver not found or retired",
        }

    current_gap = info.get("gap_s")
    if current_gap is None and info.get("position") != 1:
        return {
            "driver": driver,
            "confidence": "unavailable",
            "error": "gap data unavailable",
        }
    current_gap_s = float(current_gap or 0.0)
    rejoin_gap_s: float = current_gap_s + pit_loss_s

    # Find where driver re-joins: first car whose gap_s > rejoin_gap_s
    active = [
        (d, v)
        for d, v in cls_dict.items()
        if not v.get("retired") and d != driver and v.get("gap_s") is not None
    ]
    active.sort(key=lambda x: x[1].get("gap_s", 0))

    rejoin_pos: int = 1
    for _, rival_info in active:
        if float(rival_info["gap_s"]) < rejoin_gap_s:
            rejoin_pos += 1

    # Key rival: the car immediately ahead right now (smallest positive interval)
    current_pos = info.get("position", 99)
    key_rival: str | None = None
    rival_gap_s: float | None = None
    for d, v in cls_dict.items():
        if not v.get("retired") and d != driver:
            if v.get("position") == current_pos - 1:
                key_rival = d
                rival_gap_s = v.get("gap_s")
                break

    margin_s: float | None = None
    verdict: str

    if key_rival is None or rival_gap_s is None:
        verdict = "NO_RIVAL"
    else:
        # Undercut: gain from fresh rubber vs. extra gap to make up
        # After UNDERCUT_LAPS laps on new tyres, we close at TYRE_ADVANTAGE_PER_LAP_S/lap
        # Net margin = tyre_gain - extra_gap_created
        tyre_gain = TYRE_ADVANTAGE_PER_LAP_S * UNDERCUT_LAPS
        extra_gap = rejoin_gap_s - rival_gap_s  # how far behind rival after pit
        margin_s = round(tyre_gain - extra_gap, 3)
        verdict = "UNDERCUT_LIKELY" if margin_s > 0 else "UNLIKELY"

    return {
        "driver": driver,
        "confidence": "model",
        "evidence": {
            "pit_loss_s": pit_loss_s,
            "current_gap_s": round(current_gap_s, 3),
            "rejoin_gap_s": round(rejoin_gap_s, 3),
            "rejoin_pos": rejoin_pos,
            "key_rival": key_rival,
            "rival_gap_s": round(rival_gap_s, 3) if rival_gap_s is not None else None,
            "margin_s": margin_s,
            "verdict": verdict,
        },
    }
