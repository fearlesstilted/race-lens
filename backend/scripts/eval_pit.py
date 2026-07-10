"""Scoreboard for detect_pit_window: does "window open" precede a real stop?

The detector predicts OPPORTUNITY (free stop), not intent — so this measures
how often opportunity converts to an actual PitIn within HORIZON laps.
Baseline number for any future calibrated/ML challenger.

    python3 scripts/eval_pit.py [fixtures/*.jsonl]
"""
import json
import sys
from pathlib import Path

from racelens.events.models import Event
from racelens.insights.pit_window import detect_pit_window
from racelens.replay.engine import ReplayEngine

HORIZON_LAPS = 3
MIN_LAP = 3  # skip lap 1-2 stops: start crashes / red-flag freebies (Monaco 2024), not strategy


def eval_fixture(path: Path) -> tuple[int, int, int, int]:
    events = [Event(**json.loads(ln)) for ln in path.read_text().splitlines()]
    engine = ReplayEngine(events)

    # Lap checkpoints: first completion of each lap (≈ leader crossing the line).
    lap_t: dict[int, int] = {}
    for e in events:
        if e.type == "LapCompleted" and e.lap is not None:
            lap_t.setdefault(e.lap, e.session_time_ms)

    pits = {
        (e.driver_id, e.lap)
        for e in events
        if e.type == "PitIn" and e.driver_id and e.lap is not None and e.lap >= MIN_LAP
    }

    predicted: set[tuple[str, int]] = set()  # (driver, lap of signal)
    for lap, t in sorted(lap_t.items()):
        state = engine.state_at(t)
        for ins in detect_pit_window(state):
            predicted.add((ins["driver_ids"][0], lap))

    tp = sum(
        1 for drv, lap in predicted
        if any((drv, lap + k) in pits for k in range(1, HORIZON_LAPS + 1))
    )
    hit_pits = sum(
        1 for drv, plap in pits
        if any((drv, plap - k) in predicted for k in range(1, HORIZON_LAPS + 1))
    )
    return tp, len(predicted), len(pits), hit_pits


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(
        p for p in Path("fixtures").glob("*_race.jsonl")
    )
    tot_tp = tot_pred = tot_pits = tot_hit = 0
    print(f"{'race':28} {'precision':>9} {'recall':>7}  (signals → stops ≤{HORIZON_LAPS} laps)")
    for p in paths:
        tp, pred, pits, hit = eval_fixture(p)
        tot_tp, tot_pred = tot_tp + tp, tot_pred + pred
        tot_pits, tot_hit = tot_pits + pits, tot_hit + hit
        prec = tp / pred if pred else float("nan")
        rec = hit / pits if pits else float("nan")
        print(f"{p.stem:28} {prec:9.2%} {rec:7.2%}  ({tp}/{pred} sig, {hit}/{pits} pits)")
    prec = tot_tp / tot_pred if tot_pred else float("nan")
    rec = tot_hit / tot_pits if tot_pits else float("nan")
    print(f"{'TOTAL':28} {prec:9.2%} {rec:7.2%}")


if __name__ == "__main__":
    main()
