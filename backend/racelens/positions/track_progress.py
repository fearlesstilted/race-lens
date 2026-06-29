"""Per-tick cumulative track progress for timing-tower ordering.

progress = (lap_number - 1) + RelativeDistance, sampled onto the positions.json
tick grid so the frontend can order the timing tower by real track position
(matching the map) instead of the once-per-lap official classification.

RelativeDistance is FastF1's speed-integrated arc fraction along the lap —
reliable, unlike geometric X/Y projection (which mis-snaps on near-parallel
straights). progress is monotonic per driver; the leader is simply max(progress)
and lapped cars fall behind naturally.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def compute_progress(year: int, gp: str, session: str, session_id: str) -> dict[str, list]:
    """Return {driver_abbr: [progress|null, ...]} aligned to the positions.json grid."""
    import fastf1
    import numpy as np

    fix = Path(os.environ.get("RACELENS_FIXTURES", "fixtures"))
    pos = json.loads((fix / f"{session_id}.positions.json").read_text(encoding="utf-8"))
    start_ms = int(pos["start_ms"])
    tick_ms = int(pos["tick_ms"])
    drivers = pos["drivers"]
    n = max((len(v) for v in drivers.values()), default=0)
    # positions.json start_ms is DISPLAY time (lights-out = LIGHTS_OUT_MS); telemetry
    # below is PHYSICAL (lights-out = 0). Shift the grid back so interpolation lines up.
    LIGHTS_OUT_MS = 180_000  # must match api.LIGHTS_OUT_MS / rust LEAD_MS
    grid = np.array([start_ms + i * tick_ms - LIGHTS_OUT_MS for i in range(n)], dtype=float)

    session_map = {
        "R": "Race", "Q": "Qualifying",
        "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    }
    fastf1.Cache.enable_cache(str(Path("fastf1_cache")))
    print(f"Loading {year} {gp} {session} telemetry …", file=sys.stderr)
    ses = fastf1.get_session(year, gp, session_map.get(session.upper(), session))
    ses.load(telemetry=True, weather=False, messages=False)

    # Race-start rebase — identical to fastf1_adapter so the grid lines up.
    lap1 = ses.laps[ses.laps["LapNumber"] == 1]
    starts = (lap1["Time"] - lap1["LapTime"]).dropna()
    t0_ms = starts.min().total_seconds() * 1000 if len(starts) else 0.0

    out: dict[str, list] = {}
    for drv in ses.drivers:
        try:
            abbr = ses.get_driver(drv)["Abbreviation"]
        except Exception:
            abbr = str(drv)
        if abbr not in drivers:
            continue

        ts: list[float] = []
        ps: list[float] = []
        for _, lap in ses.laps.pick_drivers(drv).iterlaps():
            lap_no = int(lap["LapNumber"])
            try:
                tel = lap.get_telemetry()
            except Exception:
                continue
            if tel is None or len(tel) < 2 or "RelativeDistance" not in tel.columns:
                continue
            for st, rd in zip(tel["SessionTime"], tel["RelativeDistance"]):
                if st is None or rd != rd:  # NaT / NaN
                    continue
                ts.append(st.total_seconds() * 1000 - t0_ms)
                ps.append((lap_no - 1) + float(rd))

        if len(ts) < 2:
            out[abbr] = [None] * n
            continue

        order = np.argsort(ts)
        tarr = np.array(ts)[order]
        parr = np.array(ps)[order]
        vals = np.interp(grid, tarr, parr, left=np.nan, right=np.nan)
        out[abbr] = [None if v != v else round(float(v), 4) for v in vals]

    return out
