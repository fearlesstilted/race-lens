"""On-track battle detection (PLAN.md §15.4 / BATTLE_DETECTED).

A battle is a pair of neighbouring classified cars that are close on track
AND have similar pace — meaning neither car is merely lapping a backmarker
or being caught rapidly by a much faster car.

Intentionally NOT registered in the main insights registry: battles are a
separate "watch list" entity surfaced via the dedicated /battles endpoint.
"""
from __future__ import annotations

from typing import Any

BATTLE_INTERVAL_THRESHOLD_S = 1.2   # within DRS / attack range
BATTLE_PACE_DIFF_MAX_MS = 600        # lap-time difference cap (real wheel-to-wheel fight)


def detect_battles(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state.get("session_status") != "started":
        return []
    if state.get("lap", 0) < 3:
        return []

    drivers = state["drivers"]
    order = state["classification"]
    battles = []

    for defender_id, attacker_id in zip(order, order[1:]):
        defender = drivers.get(defender_id)
        attacker = drivers.get(attacker_id)
        if defender is None or attacker is None:
            continue
        if defender.get("in_pit", False) or attacker.get("in_pit", False):
            continue

        interval = attacker.get("interval_s")
        if interval is None or interval > BATTLE_INTERVAL_THRESHOLD_S:
            continue

        d_lap = defender.get("last_lap_ms")
        a_lap = attacker.get("last_lap_ms")
        if d_lap is None or a_lap is None:
            continue

        if abs(d_lap - a_lap) > BATTLE_PACE_DIFF_MAX_MS:
            continue

        def_pos = order.index(defender_id) + 1
        att_pos = def_pos + 1

        battles.append({
            "insight_id": f"battle:{defender_id}:{attacker_id}:{state['at_ms']}",
            "type": "BATTLE_DETECTED",
            "severity": "medium",
            "confidence": "high",
            "created_at_ms": state["at_ms"],
            "lap": state["lap"],
            "driver_ids": [defender_id, attacker_id],
            "evidence": {
                "interval_s": interval,
                "positions": [def_pos, att_pos],
            },
        })

    return battles
