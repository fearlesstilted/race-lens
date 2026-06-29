"""CLI: ingest a historical session and export normalized events.

    python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
    python -m racelens.cli state fixtures/monaco_2024_race.jsonl --at-ms 3600000
"""
import argparse
import json
import sys
from pathlib import Path

# Telemetry kept before lights-out (t=0) so the formation lap / grid forming is
# visible on the map. ~3 min covers a formation lap; widen if a track needs more.
# ponytail: fixed window beats trying to detect formation-lap start from the data.
PRE_START_MS = 180_000


def _detect_launch_date(ses):
    """Date of the standing-start launch (lights-out), detected from pos_data X/Y.

    The field does the formation lap (moving, spread out), holds on the grid
    (stationary, bunched) for several seconds, then launches (moves + disperses).
    Detect the last stationary hold immediately followed by sustained motion.

    Detecting in pos_data — the SAME channel that draws the map — avoids FastF1's
    per-channel clock drift (car_data / pos_data / lap timing disagree by minutes).
    Returns a pandas Timestamp, or None if no clean grid-hold-then-launch is found.
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
    # field-median per-second movement (speed) and bounding-box spread
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
                # followed by sustained motion AND the hold was bunched (a real grid,
                # not a scattered garage or a degenerate stacked-at-origin gap).
                if (len(after) and np.median(after) > move
                        and 1 < spread[i:j].mean() < spread.max() * 0.5):
                    launch = gt[j]
            i = j
        else:
            i += 1
    return pd.Timestamp(launch) if launch is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(prog="racelens")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="ingest a historical session via FastF1")
    p_ingest.add_argument("year", type=int)
    p_ingest.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_ingest.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_ingest.add_argument("-o", "--out", required=True, help="output .jsonl path")

    p_ingest_openf1 = sub.add_parser(
        "ingest-openf1", help="ingest a session via OpenF1 (no API key required)"
    )
    p_ingest_openf1.add_argument("year", type=int)
    p_ingest_openf1.add_argument("country", help='Country or circuit, e.g. "Monaco"')
    p_ingest_openf1.add_argument(
        "session", nargs="?", default="Race", help='Session name, e.g. "Race"'
    )
    p_ingest_openf1.add_argument("-o", "--out", required=True, help="output .jsonl path")

    p_capture = sub.add_parser(
        "capture-live",
        help="record the live F1 SignalR feed to a file (run DURING a live session)",
    )
    p_capture.add_argument("-o", "--out", required=True, help="output raw feed path")
    p_capture.add_argument("--timeout", type=int, default=60,
                           help="exit after N seconds with no data (0 = never)")
    p_capture.add_argument("--no-auth", action="store_true",
                           help="connect without F1 auth (may return partial/empty data)")
    p_capture.add_argument("--append", action="store_true",
                           help="append instead of overwrite (resume a capture)")

    p_ingest_live = sub.add_parser(
        "ingest-live",
        help="convert a recorded SignalR feed (capture-live) into normalized events",
    )
    p_ingest_live.add_argument("feed", nargs="+", help="recorded feed file(s)")
    p_ingest_live.add_argument("--year", type=int, required=True)
    p_ingest_live.add_argument("--gp", required=True, help='Grand Prix, e.g. "Silverstone"')
    p_ingest_live.add_argument("--session", default="R", help="R / Q / FP1 ...")
    p_ingest_live.add_argument("-o", "--out", required=True, help="output .jsonl path")

    p_track = sub.add_parser("track", help="export track outline from FastF1 telemetry")
    p_track.add_argument("year", type=int)
    p_track.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_track.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_track.add_argument("-o", "--out", required=True, help="output .track.json path")

    p_posraw = sub.add_parser(
        "positions-raw",
        help="export raw X/Y telemetry per driver as JSONL for Rust resampler",
    )
    p_posraw.add_argument("year", type=int)
    p_posraw.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_posraw.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_posraw.add_argument("-o", "--out", required=True, help="output .jsonl path")

    p_mini = sub.add_parser(
        "mini-sectors",
        help="compute near-continuous gap events from RelativeDistance telemetry",
    )
    p_mini.add_argument("year", type=int)
    p_mini.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_mini.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_mini.add_argument("session_id", help="fixture session id, e.g. monaco_2024_race")

    p_prog = sub.add_parser(
        "track-progress",
        help="write per-tick track progress into positions.json for tower ordering",
    )
    p_prog.add_argument("year", type=int)
    p_prog.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_prog.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_prog.add_argument("session_id", help="fixture session id, e.g. monaco_2024_race")

    p_state = sub.add_parser("state", help="print race state at a timestamp")
    p_state.add_argument("events_file", help="events .jsonl")
    p_state.add_argument("--at-ms", type=int, required=True)

    args = parser.parse_args()

    if args.cmd == "ingest":
        from racelens.adapters.fastf1_adapter import ingest_session
        from racelens.events.models import dump_jsonl

        events = ingest_session(args.year, args.gp, args.session)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dump_jsonl(events), encoding="utf-8")
        print(f"{len(events)} events → {out}", file=sys.stderr)

    elif args.cmd == "ingest-openf1":
        from racelens.adapters.openf1_adapter import find_session, ingest_openf1
        from racelens.events.models import dump_jsonl

        session_key = find_session(args.year, args.country, args.session)
        print(f"session_key={session_key}", file=sys.stderr)
        events = ingest_openf1(session_key)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dump_jsonl(events), encoding="utf-8")
        print(f"{len(events)} events → {out}", file=sys.stderr)

    elif args.cmd == "capture-live":
        from fastf1.livetiming.client import SignalRClient

        client = SignalRClient(
            filename=args.out,
            filemode="a" if args.append else "w",
            timeout=args.timeout,
            no_auth=args.no_auth,
        )
        print(
            f"recording live feed → {args.out} "
            f"(no_auth={args.no_auth}, timeout={args.timeout}s); Ctrl-C to stop …",
            file=sys.stderr,
        )
        client.start()  # blocks until timeout / KeyboardInterrupt

    elif args.cmd == "ingest-live":
        import fastf1

        from racelens.adapters.fastf1_adapter import ingest_live_feed
        from racelens.events.models import dump_jsonl

        cache_dir = Path("fastf1_cache")
        cache_dir.mkdir(exist_ok=True)
        fastf1.Cache.enable_cache(str(cache_dir))

        events = ingest_live_feed(*args.feed, year=args.year, gp=args.gp, session=args.session)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dump_jsonl(events), encoding="utf-8")
        print(f"{len(events)} events → {out}", file=sys.stderr)

    elif args.cmd == "track":
        import fastf1

        cache_dir = Path("fastf1_cache")
        cache_dir.mkdir(exist_ok=True)
        fastf1.Cache.enable_cache(str(cache_dir))

        session_map = {"R": "Race", "Q": "Qualifying", "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3"}
        session_name = session_map.get(args.session.upper(), args.session)

        print(f"Loading {args.year} {args.gp} {session_name} …", file=sys.stderr)
        ses = fastf1.get_session(args.year, args.gp, session_name)
        ses.load(telemetry=True)

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

        # Build session_id from the output file stem
        out_path = Path(args.out)
        stem = out_path.stem  # e.g. "monaco_2024_race.track" → need just "monaco_2024_race"
        session_id = stem[:-len(".track")] if stem.endswith(".track") else stem

        data = {
            "session_id": session_id,
            "viewbox": [VW, VH],
            "extent_dm": [x_min, y_min, x_max, y_max],
            "padding": PAD,
            "points": points,
            "corners": corners,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data), encoding="utf-8")
        print(f"{len(points)} points → {out_path}", file=sys.stderr)

    elif args.cmd == "positions-raw":
        import fastf1
        import pandas as pd

        cache_dir = Path("fastf1_cache")
        cache_dir.mkdir(exist_ok=True)
        fastf1.Cache.enable_cache(str(cache_dir))

        session_map = {
            "R": "Race", "Q": "Qualifying",
            "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
        }
        session_name = session_map.get(args.session.upper(), args.session)

        print(f"Loading {args.year} {args.gp} {session_name} …", file=sys.stderr)
        ses = fastf1.get_session(args.year, args.gp, session_name)
        ses.load(telemetry=True)

        # session_zero for Date→session-time conversion
        session_zero = pd.Timestamp(ses.date) - pd.Timedelta(ses.session_start_time)

        # Anchor t=0 to the detected standing-start launch, in the SAME Date clock
        # used below, so the map's lights-out lines up with the cars actually
        # leaving the grid. Fall back to lap-1 start if no clean grid-hold is found.
        launch_date = _detect_launch_date(ses)
        if launch_date is not None:
            t0_ms = int((launch_date - session_zero).total_seconds() * 1000)
            print(f"launch detected → t0 = {t0_ms} ms", file=sys.stderr)
        else:
            lap1 = ses.laps[ses.laps["LapNumber"] == 1]
            starts = (lap1["Time"] - lap1["LapTime"]).dropna()
            t0_td = starts.min() if len(starts) else pd.Timedelta(0)
            t0_ms = int(t0_td.total_seconds() * 1000) if not pd.isna(t0_td) else 0
            print("launch NOT detected — fell back to lap-1 start", file=sys.stderr)

        out = Path(args.out)
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

        print(f"{count} rows → {out}", file=sys.stderr)

    elif args.cmd == "mini-sectors":
        import os
        from racelens.events.models import dump_jsonl, load_jsonl
        from racelens.positions.mini_sectors import compute_gap_events

        fixtures_dir = Path(os.environ.get("RACELENS_FIXTURES", "fixtures"))
        fixture_path = fixtures_dir / f"{args.session_id}.jsonl"
        existing = load_jsonl(fixture_path.read_text(encoding="utf-8"))
        before = len(existing)

        # Drop existing per-lap gap/interval events; keep everything else
        kept = [e for e in existing if e.type not in {"GapUpdated", "IntervalUpdated"}]
        dropped = before - len(kept)

        new_events = compute_gap_events(args.year, args.gp, args.session, args.session_id)
        combined = kept + new_events
        combined.sort(key=lambda e: (e.session_time_ms, e.event_id))

        fixture_path.write_text(dump_jsonl(combined), encoding="utf-8")
        after = len(combined)
        print(
            f"before={before} dropped_gap={dropped} new_gap={len(new_events)} after={after} → {fixture_path}",
            file=sys.stderr,
        )

    elif args.cmd == "track-progress":
        import os
        from racelens.positions.track_progress import compute_progress

        fixtures_dir = Path(os.environ.get("RACELENS_FIXTURES", "fixtures"))
        pos_path = fixtures_dir / f"{args.session_id}.positions.json"
        pos = json.loads(pos_path.read_text(encoding="utf-8"))
        pos["progress"] = compute_progress(args.year, args.gp, args.session, args.session_id)
        pos_path.write_text(json.dumps(pos), encoding="utf-8")
        covered = sum(1 for arr in pos["progress"].values() if any(v is not None for v in arr))
        print(f"track-progress: {covered}/{len(pos['progress'])} drivers → {pos_path}", file=sys.stderr)

    elif args.cmd == "state":
        from racelens.events.models import load_jsonl
        from racelens.replay.engine import ReplayEngine

        events = load_jsonl(Path(args.events_file).read_text(encoding="utf-8"))
        engine = ReplayEngine(events)
        print(json.dumps(engine.state_at(args.at_ms), indent=2))


if __name__ == "__main__":
    main()
