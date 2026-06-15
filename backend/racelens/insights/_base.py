"""Shared helper for building insight dicts with a consistent structure."""
from __future__ import annotations

from typing import Any


def mk_insight(
    insight_id: str,
    type_: str,
    driver_ids: list[str],
    severity: str,
    confidence: str,
    evidence: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Return a standard insight skeleton.

    Each detector supplies its own insight_id to preserve the existing stable
    key format (frontend depends on these for React reconciliation).
    """
    return {
        "insight_id": insight_id,
        "type": type_,
        "severity": severity,
        "confidence": confidence,
        "created_at_ms": state["at_ms"],
        "lap": state["lap"],
        "driver_ids": driver_ids,
        "evidence": evidence,
    }
