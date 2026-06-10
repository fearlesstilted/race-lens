"""Traffic risk: a faster driver stuck behind a slower car (PLAN.md §12.3).

Pure function over race state — deterministic, no I/O, no AI. Insights are
structured data first; text rendering happens elsewhere.
"""
from __future__ import annotations

from typing import Any

INTERVAL_THRESHOLD_S = 1.0   # within striking distance
PACE_DELTA_MEDIUM_MS = 200   # behind car is at least this much faster per lap
PACE_DELTA_HIGH_MS = 500


def detect_traffic_risk(state: dict[str, Any]) -> list[dict[str, Any]]:
    drivers = state["drivers"]
    order = state["classification"]
    insights = []

    for ahead_id, behind_id in zip(order, order[1:]):
        ahead, behind = drivers[ahead_id], drivers[behind_id]
        interval = behind["interval_s"]
        if interval is None or interval > INTERVAL_THRESHOLD_S:
            continue
        if behind["last_lap_ms"] is None or ahead["last_lap_ms"] is None:
            continue
        if behind["in_pit"] or ahead["in_pit"]:
            continue
        pace_delta_ms = ahead["last_lap_ms"] - behind["last_lap_ms"]
        if pace_delta_ms < PACE_DELTA_MEDIUM_MS:
            continue

        severity = "high" if pace_delta_ms >= PACE_DELTA_HIGH_MS else "medium"
        insights.append({
            "insight_id": f"traffic:{behind_id}:{state['at_ms']}",
            "type": f"TRAFFIC_RISK_{severity.upper()}",
            "severity": severity,
            "confidence": "high" if behind["laps_completed"] >= 2 else "medium",
            "created_at_ms": state["at_ms"],
            "lap": state["lap"],
            "driver_ids": [behind_id, ahead_id],
            "evidence": {
                "interval_s": interval,
                "pace_delta_ms": pace_delta_ms,
                "behind_last_lap_ms": behind["last_lap_ms"],
                "ahead_last_lap_ms": ahead["last_lap_ms"],
            },
        })
    return insights
