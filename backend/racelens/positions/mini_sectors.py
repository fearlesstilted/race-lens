"""Near-continuous gap/interval events from FastF1 RelativeDistance telemetry.

Computes GapUpdated and IntervalUpdated events at K evenly-spaced gate
fractions around each lap. The gate crossing time is derived by linear
interpolation of the SessionTime channel when RelativeDistance crosses a
gate fraction. This gives ~20x more gap updates than the per-lap baseline.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

K = 20  # gates per lap


def _ms(td) -> int | None:
    """pandas Timedelta → whole milliseconds, None for NaT."""
    import pandas as pd

    if td is None or pd.isna(td):
        return None
    return int(td.total_seconds() * 1000)


def compute_gap_events(
    year: int,
    gp: str,
    session: str,
    session_id: str,
) -> list[Any]:
    """Load session telemetry and return GapUpdated/IntervalUpdated events.

    Uses FastF1 RelativeDistance channel (0..1 per lap, speed-integrated).
    Rebases all session_time_ms to match existing fastf1_adapter events.
    """
    import fastf1

    from racelens.events.models import event

    session_map = {
        "R": "Race",
        "Q": "Qualifying",
        "FP1": "Practice 1",
        "FP2": "Practice 2",
        "FP3": "Practice 3",
    }
    session_name = session_map.get(session.upper(), session)

    cache_dir = Path("fastf1_cache")
    cache_dir.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    print(f"Loading {year} {gp} {session_name} telemetry …", file=sys.stderr)
    ses = fastf1.get_session(year, gp, session_name)
    ses.load(telemetry=True, weather=False, messages=False)

    # Rebase to race start — identical to fastf1_adapter.
    from racelens.adapters._common import fastf1_lap1_start

    lap1 = ses.laps[ses.laps["LapNumber"] == 1]
    t0_ms = _ms(fastf1_lap1_start(lap1)) or 0

    gates = [i / K for i in range(1, K + 1)]  # 0.05, 0.10, …, 1.00

    # crossings[lap_number][gate_idx] = list of (rebased_ms, driver)
    crossings: dict[tuple[int, int], list[tuple[int, str]]] = {}

    for drv in ses.drivers:
        try:
            drv_laps = ses.laps.pick_drivers(drv)
        except Exception:
            continue
        try:
            abbr = ses.get_driver(drv)["Abbreviation"]
        except Exception:
            abbr = str(drv)

        for _, lap in drv_laps.iterlaps():
            lap_no = int(lap["LapNumber"])
            try:
                tel = lap.get_telemetry()
            except Exception:
                continue
            if tel is None or len(tel) < 2:
                continue
            if "RelativeDistance" not in tel.columns or "SessionTime" not in tel.columns:
                continue

            rd = tel["RelativeDistance"].to_numpy()
            st = tel["SessionTime"]

            # Convert SessionTime (Timedelta from session start) to rebased ms
            st_ms = []
            for td in st:
                v = _ms(td)
                if v is None:
                    st_ms.append(None)
                else:
                    st_ms.append(v - t0_ms)

            # Walk through samples looking for gate crossings
            gate_idx = 0
            n = len(rd)
            for i in range(1, n):
                while gate_idx < len(gates) and rd[i] >= gates[gate_idx]:
                    # Check if this is a genuine crossing (not a wrap-around reset)
                    if rd[i - 1] <= gates[gate_idx]:
                        g = gates[gate_idx]
                        # Linear interpolation
                        rd0, rd1 = rd[i - 1], rd[i]
                        frac = (g - rd0) / (rd1 - rd0) if rd1 != rd0 else 0.0
                        t0_v = st_ms[i - 1]
                        t1_v = st_ms[i]
                        if t0_v is not None and t1_v is not None:
                            t_cross = round(t0_v + frac * (t1_v - t0_v))
                            key = (lap_no, gate_idx)
                            crossings.setdefault(key, []).append((t_cross, abbr))
                    gate_idx += 1
                if gate_idx >= len(gates):
                    break

    events: list[Any] = []
    src = "mini_sectors"

    for (lap_no, _gate_idx), cars in crossings.items():
        cars.sort(key=lambda x: x[0])
        leader_t = cars[0][0]
        prev_t = leader_t
        for rank, (t, drv) in enumerate(cars):
            if rank == 0:
                prev_t = t
                continue
            gap_s = round((t - leader_t) / 1000, 3)
            interval_s = round((t - prev_t) / 1000, 3)
            events.append(
                event(
                    session_id,
                    "GapUpdated",
                    t,
                    drv,
                    lap=lap_no,
                    source=src,
                    gap_s=gap_s,
                )
            )
            events.append(
                event(
                    session_id,
                    "IntervalUpdated",
                    t,
                    drv,
                    lap=lap_no,
                    source=src,
                    interval_s=interval_s,
                )
            )
            prev_t = t

    return events
