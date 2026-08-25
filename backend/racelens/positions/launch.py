"""Standing-start launch detection (lights-out), shared by the positions pipeline.

The map (pos_data X/Y) and the timing-tower order (track progress) must share one
time anchor or they drift apart. FastF1's channels disagree by minutes, so instead
of trusting any clock we detect the launch physically — cars hold on the grid
(stationary + bunched) then disperse — from pos_data, and anchor everything to its
absolute Date. Both positions-raw and track-progress use this.
"""
from __future__ import annotations

from statistics import fmean, median


def _first_launch_index(speed, spread, *, stop: float, move: float,
                        hold: int = 6, after_n: int = 20) -> int | None:
    stationary = [value < stop for value in speed]
    max_spread = max(spread, default=0)
    i = 0
    while i < len(stationary):
        if not stationary[i]:
            i += 1
            continue
        j = i
        while j < len(stationary) and stationary[j]:
            j += 1
        after = speed[j:j + after_n]
        if (
            j - i >= hold
            and len(after)
            and median(after) > move
            and 1 < fmean(spread[i:j]) < max_spread * 0.5
        ):
            return j
        i = j
    return None


def detect_launch_date(ses):
    """Absolute Date of the standing-start launch, from pos_data X/Y motion.

    Returns a pandas Timestamp, or None if no clean grid-hold-then-launch is found
    (callers fall back to the lap-1 start time).
    """
    import numpy as np
    import pandas as pd

    cars = []
    for dn in ses.pos_data:
        df = ses.pos_data[dn]
        if df is None or len(df) < 10:
            continue
        cars.append((df["Date"].to_numpy(),
                     df["X"].to_numpy().astype(float),
                     df["Y"].to_numpy().astype(float)))
    if len(cars) < 10:
        return None

    d0 = min(c[0][0] for c in cars)
    d1 = max(c[0][-1] for c in cars)
    gt = pd.date_range(d0, d1, freq="1s").to_numpy()

    def samp(dates, arr):
        return arr[np.clip(np.searchsorted(dates, gt), 0, len(arr) - 1)]

    xs = np.array([samp(d, x) for d, x, y in cars])
    ys = np.array([samp(d, y) for d, x, y in cars])
    speed = np.concatenate([[0.0],
                            np.median(np.hypot(np.diff(xs, axis=1), np.diff(ys, axis=1)), axis=0)])
    spread = (xs.max(0) - xs.min(0)) + (ys.max(0) - ys.min(0))

    mx = np.percentile(speed, 95) or 1.0
    stop, move, hold, after_n = mx * 0.05, mx * 0.4, 6, 20
    launch = _first_launch_index(
        speed, spread, stop=stop, move=move, hold=hold, after_n=after_n,
    )
    return pd.Timestamp(gt[launch]) if launch is not None else None


def detect_launch_ms(ses) -> int | None:
    """Standing-start launch in FastF1 session-time milliseconds."""
    launch_date = detect_launch_date(ses)
    if launch_date is None:
        return None
    session_zero = ses.date - ses.session_start_time
    return int((launch_date - session_zero).total_seconds() * 1000)
