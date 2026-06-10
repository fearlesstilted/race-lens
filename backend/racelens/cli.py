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

    elif args.cmd == "state":
        from racelens.events.models import load_jsonl
        from racelens.replay.engine import ReplayEngine

        events = load_jsonl(Path(args.events_file).read_text(encoding="utf-8"))
        engine = ReplayEngine(events)
        print(json.dumps(engine.state_at(args.at_ms), indent=2))


if __name__ == "__main__":
    main()
