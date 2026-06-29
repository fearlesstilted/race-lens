"""CLI: ingest a historical session and export normalized events.

    python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
    python -m racelens.cli state fixtures/monaco_2024_race.jsonl --at-ms 3600000
"""
import argparse
import json
import sys
from pathlib import Path


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

        # Compute t0 rebase identical to fastf1_adapter: earliest lap-1 start = min(Time - LapTime)
        lap1 = ses.laps[ses.laps["LapNumber"] == 1]
        starts = (lap1["Time"] - lap1["LapTime"]).dropna()
        t0_td = starts.min() if len(starts) else pd.Timedelta(0)
        t0_ms = int(t0_td.total_seconds() * 1000) if not pd.isna(t0_td) else 0

        # session_zero for Date→session-time conversion (same as fastf1_adapter race control path)
        session_zero = pd.Timestamp(ses.date) - pd.Timedelta(ses.session_start_time)

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
                    if t_ms < -60000:
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
