"""Tyre stint timeline.

Builds, per driver, the sequence of tyre stints across the race from the
TyreStintUpdated + LapCompleted event stream. Each stint is a compound held
over a contiguous range of laps — the raw material for the strategy timeline
(compound-coloured bars, length = laps).
"""
from __future__ import annotations

from typing import Any


def stint_timeline(events: list[Any], total_laps: int) -> dict[str, list[dict]]:
    """Return {driver: [{compound, start_lap, end_lap, laps}, ...]}.

    The starting tyre (TyreStintUpdated at t=0, lap=None) opens stint 1 at lap 1.
    Each later TyreStintUpdated (a pit stop) opens a new stint at its lap. A
    stint ends the lap before the next one starts; the final stint ends at the
    driver's last completed lap (capped at total_laps) so retirements don't draw
    a phantom bar to the finish.
    """
    raw: dict[str, list[tuple[int, str]]] = {}
    last_lap: dict[str, int] = {}

    for e in events:
        drv = e.driver_id
        if drv is None:
            continue
        if e.type == "LapCompleted" and e.lap:
            last_lap[drv] = max(last_lap.get(drv, 0), int(e.lap))
        elif e.type == "TyreStintUpdated":
            start = int(e.lap) if e.lap else 1
            compound = (e.payload or {}).get("compound") or "UNKNOWN"
            raw.setdefault(drv, []).append((start, compound))

    out: dict[str, list[dict]] = {}
    for drv, stints in raw.items():
        # Collapse multiple entries that share a start lap (e.g. starting-tyre
        # event + a lap-1 pit) — the last compound seen is the one actually run.
        by_start: dict[int, str] = {}
        for start, compound in stints:  # event order preserved → last wins
            by_start[start] = compound
        ordered = sorted(by_start.items())
        drv_end = min(total_laps, last_lap.get(drv, total_laps) or total_laps)
        rows: list[dict] = []
        for i, (start, compound) in enumerate(ordered):
            end = ordered[i + 1][0] - 1 if i + 1 < len(ordered) else drv_end
            if end < start:
                end = start
            rows.append({
                "compound": compound,
                "start_lap": start,
                "end_lap": end,
                "laps": end - start + 1,
            })
        out[drv] = rows
    return out
