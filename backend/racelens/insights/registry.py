"""Single entry point: all insight detectors over one state."""
from typing import Any

from racelens.insights.drs_train import detect_drs_train
from racelens.insights.pit_window import detect_pit_window
from racelens.insights.traffic import detect_traffic_risk

DETECTORS = (detect_traffic_risk, detect_drs_train, detect_pit_window)


def detect_all(state: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for d in DETECTORS:
        out.extend(d(state))
    return out
