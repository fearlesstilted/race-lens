"""Standing-start launch detection (lights-out), shared by the positions pipeline.

The map (pos_data X/Y) and the timing-tower order (track progress) must share one
time anchor or they drift apart. FastF1's channels disagree by minutes, so instead
of trusting any clock we detect the launch physically — cars hold on the grid
(stationary + bunched) then disperse — from pos_data, and anchor everything to its
absolute Date. Both positions-raw and track-progress use this.
"""
from __future__ import annotations


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
    stationary = speed < stop
    launch = None
    i = 0
    while i < len(stationary):
        if stationary[i]:
            j = i
            while j < len(stationary) and stationary[j]:
                j += 1
            if (j - i) >= hold:
                after = speed[j:j + after_n]
                if (len(after) and np.median(after) > move
                        and 1 < spread[i:j].mean() < spread.max() * 0.5):
                    launch = gt[j]
            i = j
        else:
            i += 1
    return pd.Timestamp(launch) if launch is not None else None
