"""CLI: ingest a historical session and export normalized events.

    python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
    python -m racelens.cli state fixtures/monaco_2024_race.jsonl --at-ms 3600000
"""
import argparse
import json
import sys
from pathlib import Path


def _write_events(events, out: str) -> None:
    """Shared tail of every ingest command: dump events, report to stderr."""
    from racelens.events.models import dump_jsonl

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dump_jsonl(events), encoding="utf-8")
    print(f"{len(events)} events → {out_path}", file=sys.stderr)


# ── Subcommand handlers ────────────────────────────────────────────────────────

def _cmd_ingest(args: argparse.Namespace) -> None:
    from racelens.adapters.fastf1_adapter import ingest_session

    _write_events(ingest_session(args.year, args.gp, args.session), args.out)


def _cmd_ingest_openf1(args: argparse.Namespace) -> None:
    from racelens.adapters.openf1_adapter import find_session, ingest_openf1

    session_key = find_session(args.year, args.country, args.session)
    print(f"session_key={session_key}", file=sys.stderr)
    _write_events(ingest_openf1(session_key), args.out)


def _cmd_capture_live(args: argparse.Namespace) -> None:
    from fastf1.livetiming.client import SignalRClient

    if args.no_auth:
        # ponytail: fastf1 3.8.3 bug — no_auth passes access_token_factory=None,
        # signalrcore rejects non-callable. Strip the key. Drop when fastf1 fixes.
        from signalrcore.hub_connection_builder import HubConnectionBuilder

        _orig_with_url = HubConnectionBuilder.with_url

        def _with_url_no_none_factory(self, url, options=None):
            if options and options.get("access_token_factory") is None:
                options = {k: v for k, v in options.items() if k != "access_token_factory"}
            return _orig_with_url(self, url, options=options)

        HubConnectionBuilder.with_url = _with_url_no_none_factory

    client = SignalRClient(
        filename=args.out,
        filemode="a" if args.append else "w",
        timeout=args.timeout,
        no_auth=args.no_auth,
    )
    # Record real car coordinates too (fastf1's default topic list omits them).
    # Costs file size only; enables a real live map (decode is a separate step).
    if "Position.z" not in client.topics:
        client.topics.append("Position.z")
    print(
        f"recording live feed → {args.out} "
        f"(no_auth={args.no_auth}, timeout={args.timeout}s); Ctrl-C to stop …",
        file=sys.stderr,
    )
    client.start()  # blocks until timeout / KeyboardInterrupt


def _cmd_ingest_live(args: argparse.Namespace) -> None:
    import fastf1

    from racelens.adapters.fastf1_adapter import ingest_live_feed

    cache_dir = Path("fastf1_cache")
    cache_dir.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    events = ingest_live_feed(*args.feed, year=args.year, gp=args.gp, session=args.session)
    _write_events(events, args.out)


def _cmd_track(args: argparse.Namespace) -> None:
    from racelens.positions.track import build_track_outline

    # Build session_id from the output file stem
    out_path = Path(args.out)
    stem = out_path.stem  # e.g. "monaco_2024_race.track" → need just "monaco_2024_race"
    session_id = stem[:-len(".track")] if stem.endswith(".track") else stem

    data = build_track_outline(args.year, args.gp, args.session, session_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data), encoding="utf-8")
    print(f"{len(data['points'])} points → {out_path}", file=sys.stderr)


def _cmd_positions_raw(args: argparse.Namespace) -> None:
    from racelens.positions.track import export_raw_positions

    out = Path(args.out)
    count = export_raw_positions(args.year, args.gp, args.session, out)
    print(f"{count} rows → {out}", file=sys.stderr)


def _cmd_mini_sectors(args: argparse.Namespace) -> None:
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


def _cmd_track_progress(args: argparse.Namespace) -> None:
    import os

    from racelens.positions.track_progress import compute_progress

    fixtures_dir = Path(os.environ.get("RACELENS_FIXTURES", "fixtures"))
    pos_path = fixtures_dir / f"{args.session_id}.positions.json"
    pos = json.loads(pos_path.read_text(encoding="utf-8"))
    pos["progress"] = compute_progress(args.year, args.gp, args.session, args.session_id)
    pos_path.write_text(json.dumps(pos), encoding="utf-8")
    covered = sum(1 for arr in pos["progress"].values() if any(v is not None for v in arr))
    print(f"track-progress: {covered}/{len(pos['progress'])} drivers → {pos_path}", file=sys.stderr)


def _cmd_radio_transcribe(args: argparse.Namespace) -> None:
    from racelens.radio.transcribe import enrich_fixture

    done = enrich_fixture(Path(args.fixture))
    print(f"radio-transcribe: {done} transcripts → {args.fixture}", file=sys.stderr)


def _cmd_state(args: argparse.Namespace) -> None:
    from racelens.events.models import load_jsonl
    from racelens.replay.engine import ReplayEngine

    events = load_jsonl(Path(args.events_file).read_text(encoding="utf-8"))
    engine = ReplayEngine(events)
    print(json.dumps(engine.state_at(args.at_ms), indent=2))


# ── Parser / dispatch ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(prog="racelens")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="ingest a historical session via FastF1")
    p_ingest.add_argument("year", type=int)
    p_ingest.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_ingest.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_ingest.add_argument("-o", "--out", required=True, help="output .jsonl path")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_ingest_openf1 = sub.add_parser(
        "ingest-openf1", help="ingest a session via OpenF1 (no API key required)"
    )
    p_ingest_openf1.add_argument("year", type=int)
    p_ingest_openf1.add_argument("country", help='Country or circuit, e.g. "Monaco"')
    p_ingest_openf1.add_argument(
        "session", nargs="?", default="Race", help='Session name, e.g. "Race"'
    )
    p_ingest_openf1.add_argument("-o", "--out", required=True, help="output .jsonl path")
    p_ingest_openf1.set_defaults(func=_cmd_ingest_openf1)

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
    p_capture.set_defaults(func=_cmd_capture_live)

    p_ingest_live = sub.add_parser(
        "ingest-live",
        help="convert a recorded SignalR feed (capture-live) into normalized events",
    )
    p_ingest_live.add_argument("feed", nargs="+", help="recorded feed file(s)")
    p_ingest_live.add_argument("--year", type=int, required=True)
    p_ingest_live.add_argument("--gp", required=True, help='Grand Prix, e.g. "Silverstone"')
    p_ingest_live.add_argument("--session", default="R", help="R / Q / FP1 ...")
    p_ingest_live.add_argument("-o", "--out", required=True, help="output .jsonl path")
    p_ingest_live.set_defaults(func=_cmd_ingest_live)

    p_track = sub.add_parser("track", help="export track outline from FastF1 telemetry")
    p_track.add_argument("year", type=int)
    p_track.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_track.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_track.add_argument("-o", "--out", required=True, help="output .track.json path")
    p_track.set_defaults(func=_cmd_track)

    p_posraw = sub.add_parser(
        "positions-raw",
        help="export raw X/Y telemetry per driver as JSONL for Rust resampler",
    )
    p_posraw.add_argument("year", type=int)
    p_posraw.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_posraw.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_posraw.add_argument("-o", "--out", required=True, help="output .jsonl path")
    p_posraw.set_defaults(func=_cmd_positions_raw)

    p_mini = sub.add_parser(
        "mini-sectors",
        help="compute near-continuous gap events from RelativeDistance telemetry",
    )
    p_mini.add_argument("year", type=int)
    p_mini.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_mini.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_mini.add_argument("session_id", help="fixture session id, e.g. monaco_2024_race")
    p_mini.set_defaults(func=_cmd_mini_sectors)

    p_prog = sub.add_parser(
        "track-progress",
        help="write per-tick track progress into positions.json for tower ordering",
    )
    p_prog.add_argument("year", type=int)
    p_prog.add_argument("gp", help='Grand Prix name, e.g. "Monaco"')
    p_prog.add_argument("session", nargs="?", default="R", help="R / Q / FP1 ...")
    p_prog.add_argument("session_id", help="fixture session id, e.g. monaco_2024_race")
    p_prog.set_defaults(func=_cmd_track_progress)

    p_radio = sub.add_parser(
        "radio-transcribe", help="whisper-transcribe a fixture's team-radio clips in place"
    )
    p_radio.add_argument("fixture", help="replay fixture .jsonl with audio_url radio events")
    p_radio.set_defaults(func=_cmd_radio_transcribe)

    p_state = sub.add_parser("state", help="print race state at a timestamp")
    p_state.add_argument("events_file", help="events .jsonl")
    p_state.add_argument("--at-ms", type=int, required=True)
    p_state.set_defaults(func=_cmd_state)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
