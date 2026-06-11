"""Clean air pace insight (PLAN.md §12.3 / CLEAN_AIR_PACE_LEADER).

Identifies the fastest driver running in unobstructed air and flags when
that driver is lapping quicker than the race leader — a strategic signal.
"""
from __future__ import annotations

from typing import Any

CLEAN_AIR_INTERVAL_THRESHOLD_S = 2.5   # gap beyond which a driver is in clear air
MIN_LAPS_WINDOW = 3                     # recent_laps_ms must have exactly 3 entries

_NEUTRALIZATION_STATUSES = {"red_flag", "safety_car", "vsc"}


def detect_clean_air_pace(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("session_status") != "started":
        return []

    drivers = state["drivers"]
    order = state["classification"]
    if not order:
        return []

    # Collect drivers in clean air
    clean_air: list[tuple[str, float]] = []  # (driver_id, avg_lap_ms)
    for drv_id in order:
        d = drivers.get(drv_id)
        if d is None:
            continue
        if d.get("in_pit", False):
            continue
        laps = d.get("recent_laps_ms", [])
        if len(laps) != MIN_LAPS_WINDOW:
            continue
        interval = d.get("interval_s")   # None means race leader
        if interval is not None and interval <= CLEAN_AIR_INTERVAL_THRESHOLD_S:
            continue
        avg = sum(laps) / len(laps)
        clean_air.append((drv_id, avg))

    if not clean_air:
        return []

    # Fastest in clean air
    fastest_id, fastest_avg = min(clean_air, key=lambda x: x[1])

    # Race leader pace (classification[0]) — only if they have 3 recent laps
    leader_id = order[0]
    leader_laps = drivers.get(leader_id, {}).get("recent_laps_ms", [])
    if len(leader_laps) == MIN_LAPS_WINDOW:
        leader_avg = sum(leader_laps) / len(leader_laps)
        vs_race_leader_ms: float | None = round(fastest_avg - leader_avg, 1)
    else:
        vs_race_leader_ms = None

    # severity: medium when fastest clean-air car is quicker than the leader
    if vs_race_leader_ms is not None and vs_race_leader_ms < 0:
        severity = "medium"
    else:
        severity = "info"

    return [
        {
            "insight_id": f"clean_air_pace:{fastest_id}:{state['at_ms']}",
            "type": "CLEAN_AIR_PACE_LEADER",
            "severity": severity,
            "confidence": "high",
            "created_at_ms": state["at_ms"],
            "lap": state["lap"],
            "driver_ids": [fastest_id],
            "evidence": {
                "avg_lap_ms": round(fastest_avg, 1),
                "vs_race_leader_ms": vs_race_leader_ms,
                "drivers_in_clean_air": len(clean_air),
            },
        }
    ]
