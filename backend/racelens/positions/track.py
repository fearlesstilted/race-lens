"""Track geometry exports from FastF1 telemetry.

build_track_outline: fastest-lap X/Y → normalized 600x400 outline + corner
markers (the .track.json consumed by the frontend map).
export_raw_positions: per-driver raw X/Y rows as JSONL for the Rust resampler.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Telemetry kept before lights-out (t=0) so the formation lap / grid forming is
# visible on the map. ~3 min covers a formation lap; widen if a track needs more.
# A fixed window is more reliable than inferring formation-lap start from telemetry.
PRE_START_MS = 180_000

SESSION_NAME_MAP = {
    "R": "Race", "Q": "Qualifying",
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
}


def _load_session(year: int, gp: str, session: str):
    """Load a FastF1 session with telemetry, using the local cache dir."""
    import fastf1

    import os

    cache_dir = Path(os.environ.get("FASTF1_CACHE", "fastf1_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    session_name = SESSION_NAME_MAP.get(session.upper(), session)
    print(f"Loading {year} {gp} {session_name} …", file=sys.stderr)
    ses = fastf1.get_session(year, gp, session_name)
    ses.load(telemetry=True)
    return ses


def build_track_outline(year: int, gp: str, session: str, session_id: str) -> dict[str, Any]:
    """Fastest-lap X/Y → the .track.json payload (outline points + corners)."""
    ses = _load_session(year, gp, session)

    lap = ses.laps.pick_fastest()
    pos = lap.get_pos_data()

    xs = pos["X"].to_numpy()
    ys = pos["Y"].to_numpy()

    # Downsample to ~400 points uniformly
    n = len(xs)
    target = 400
    if n > target:
        step = n / target
        indices = [round(i * step) for i in range(target)]
        indices = [min(i, n - 1) for i in indices]
        xs = xs[indices]
        ys = ys[indices]

    # Normalize to viewBox 600x400 with padding 20, preserve aspect, invert Y
    VW, VH = 600, 400
    PAD = 20
    x_min, x_max = float(xs.min()), float(xs.max())
    y_min, y_max = float(ys.min()), float(ys.max())
    x_range = x_max - x_min or 1.0
    y_range = y_max - y_min or 1.0
    avail_w = VW - 2 * PAD
    avail_h = VH - 2 * PAD
    scale = min(avail_w / x_range, avail_h / y_range)
    # Center the smaller axis
    offset_x = PAD + (avail_w - x_range * scale) / 2
    offset_y = PAD + (avail_h - y_range * scale) / 2

    points = []
    for x, y in zip(xs, ys):
        nx = round(offset_x + (x - x_min) * scale, 1)
        # invert Y
        ny = round(VH - (offset_y + (y - y_min) * scale), 1)
        points.append([nx, ny])

    # Close contour: ensure last point == first
    if points and points[0] != points[-1]:
        points.append(points[0])

    # Corners (turn numbers) — same normalization as points
    corners = []
    try:
        circuit_info = ses.get_circuit_info()
        if circuit_info is not None and hasattr(circuit_info, "corners"):
            for _, row in circuit_info.corners.iterrows():
                cx = round(offset_x + (float(row["X"]) - x_min) * scale, 1)
                cy = round(VH - (offset_y + (float(row["Y"]) - y_min) * scale), 1)
                corners.append({"number": int(row["Number"]), "x": cx, "y": cy})
    except Exception:
        corners = []

    return {
        "session_id": session_id,
        "viewbox": [VW, VH],
        "extent_dm": [x_min, y_min, x_max, y_max],
        "padding": PAD,
        "points": points,
        "corners": corners,
    }


def export_raw_positions(year: int, gp: str, session: str, out: Path) -> int:
    """Write per-driver raw X/Y telemetry rows as JSONL; return the row count.

    t=0 is anchored to the detected standing-start launch (fallback: lap-1
    start) and rows earlier than PRE_START_MS before it are dropped.
    """
    import pandas as pd

    ses = _load_session(year, gp, session)

    # session_zero for Date→session-time conversion
    session_zero = pd.Timestamp(ses.date) - pd.Timedelta(ses.session_start_time)

    # Anchor t=0 to the detected standing-start launch, in the SAME Date clock
    # used below, so the map's lights-out lines up with the cars actually
    # leaving the grid. Fall back to lap-1 start if no clean grid-hold is found.
    from racelens.positions.launch import detect_launch_ms
    t0_ms = detect_launch_ms(ses)
    if t0_ms is not None:
        print(f"launch detected → t0 = {t0_ms} ms", file=sys.stderr)
    else:
        lap1 = ses.laps[ses.laps["LapNumber"] == 1]
        starts = (lap1["Time"] - lap1["LapTime"]).dropna()
        t0_td = starts.min() if len(starts) else pd.Timedelta(0)
        t0_ms = int(t0_td.total_seconds() * 1000) if not pd.isna(t0_td) else 0
        print("launch NOT detected — fell back to lap-1 start", file=sys.stderr)

    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out.open("w", encoding="utf-8") as fh:
        for drv_num in ses.pos_data:
            try:
                drv_abbr = ses.get_driver(str(drv_num))["Abbreviation"]
            except Exception:
                drv_abbr = str(drv_num)
            pos_df = ses.pos_data[drv_num]
            if pos_df is None or len(pos_df) == 0:
                continue
            for row in pos_df.itertuples():
                # Date column is absolute timestamp → session-relative ms → rebase
                try:
                    date_ts = pd.Timestamp(row.Date)
                    t_ms = int((date_ts - session_zero).total_seconds() * 1000) - t0_ms
                except Exception:
                    continue
                if t_ms < -PRE_START_MS:
                    continue
                try:
                    x = float(row.X)
                    y = float(row.Y)
                except Exception:
                    continue
                line = json.dumps({"driver": drv_abbr, "t_ms": t_ms, "x": x, "y": y})
                fh.write(line + "\n")
                count += 1

    return count
