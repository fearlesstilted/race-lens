"""DRS train: a chain of 3+ cars each within ~1s of the car ahead (PLAN.md §12.3).

Pure function over race state, like traffic risk. The head of the train is
the car that everyone is stuck behind.
"""
from __future__ import annotations

from typing import Any

CHAIN_INTERVAL_S = 1.0
MIN_TRAIN_SIZE = 3  # cars including the head
MAX_TRAIN_SIZE = 8  # larger chains are SC/race-start compression, not a DRS train


def detect_drs_train(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state["lap"] < 3:
        return []

    drivers = state["drivers"]
    order = state["classification"]
    insights = []

    chain: list[str] = []
    for ahead_id, behind_id in zip(order, order[1:]):
        interval = drivers[behind_id]["interval_s"]
        linked = (
            interval is not None
            and interval <= CHAIN_INTERVAL_S
            and not drivers[behind_id]["in_pit"]
            and not drivers[ahead_id]["in_pit"]
        )
        if linked:
            if not chain:
                chain = [ahead_id]
            chain.append(behind_id)
        else:
            if MIN_TRAIN_SIZE <= len(chain) <= MAX_TRAIN_SIZE:
                insights.append(_train(state, chain))
            chain = []
    if MIN_TRAIN_SIZE <= len(chain) <= MAX_TRAIN_SIZE:
        insights.append(_train(state, chain))
    return insights


def _train(state: dict[str, Any], chain: list[str]) -> dict[str, Any]:
    drivers = state["drivers"]
    return {
        "insight_id": f"drs_train:{chain[0]}:{state['at_ms']}",
        "type": "DRS_TRAIN_ACTIVE",
        "severity": "medium" if len(chain) < 5 else "high",
        "confidence": "high",
        "created_at_ms": state["at_ms"],
        "lap": state["lap"],
        "driver_ids": list(chain),  # head first
        "evidence": {
            "cars": len(chain),
            "head": chain[0],
            "intervals_s": [drivers[d]["interval_s"] for d in chain[1:]],
        },
    }
