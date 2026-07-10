"""Walk-forward scoreboard for the replay forecast layer.

Run from ``backend``:

    python scripts/evaluate_forecast.py
"""
from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from racelens.events.models import load_jsonl
from racelens.forecast.projection import project_order
from racelens.forecast.win_prob import win_probability
from racelens.replay.engine import ReplayEngine


@dataclass
class Score:
    checkpoints: int = 0
    current_errors: list[float] = field(default_factory=list)
    outlook_errors: list[float] = field(default_factory=list)
    current_winner_hits: int = 0
    outlook_winner_hits: int = 0
    invalid_leader_gaps: int = 0
    win_score_brier: list[float] = field(default_factory=list)

    def extend(self, other: "Score") -> None:
        self.checkpoints += other.checkpoints
        self.current_errors.extend(other.current_errors)
        self.outlook_errors.extend(other.outlook_errors)
        self.current_winner_hits += other.current_winner_hits
        self.outlook_winner_hits += other.outlook_winner_hits
        self.invalid_leader_gaps += other.invalid_leader_gaps
        self.win_score_brier.extend(other.win_score_brier)


def _mae(order: list[str], final_positions: dict[str, int]) -> float | None:
    positions = {driver: position for position, driver in enumerate(order, start=1)}
    errors = [
        abs(positions[driver] - final_position)
        for driver, final_position in final_positions.items()
        if driver in positions
    ]
    return statistics.mean(errors) if errors else None


def evaluate(path: Path) -> Score:
    events = load_jsonl(path.read_text())
    engine = ReplayEngine(events)
    final_state = engine.state_at(max(event.session_time_ms for event in events))
    final_order = final_state["classification"]
    final_positions = {driver: position for position, driver in enumerate(final_order, start=1)}
    winner = final_order[0]

    lap_times: dict[int, int] = {}
    for event in events:
        if event.lap is not None:
            lap_times[event.lap] = max(lap_times.get(event.lap, 0), event.session_time_ms)

    score = Score()
    final_lap = max(lap_times, default=0)
    for lap, at_ms in sorted(lap_times.items()):
        if lap < 3 or lap >= final_lap:
            continue
        state = engine.state_at(at_ms)
        current_order = state["classification"]
        outlook_order = project_order(state)["projected_order"]
        if not current_order or not outlook_order:
            continue

        current_mae = _mae(current_order, final_positions)
        outlook_mae = _mae(outlook_order, final_positions)
        if current_mae is None or outlook_mae is None:
            continue

        score.checkpoints += 1
        score.current_errors.append(current_mae)
        score.outlook_errors.append(outlook_mae)
        score.current_winner_hits += current_order[0] == winner
        score.outlook_winner_hits += outlook_order[0] == winner

        leader = current_order[0]
        if state["drivers"][leader].get("gap_s") != 0.0:
            score.invalid_leader_gaps += 1

        win_score = win_probability(state, state["session_id"])["win_score"]
        score.win_score_brier.append(
            sum((win_score.get(driver, 0.0) - (driver == winner)) ** 2 for driver in final_order)
        )
    return score


def _format(name: str, score: Score) -> str:
    current_mae = statistics.mean(score.current_errors or [0.0])
    outlook_mae = statistics.mean(score.outlook_errors or [0.0])
    brier = statistics.mean(score.win_score_brier or [0.0])
    return (
        f"{name:<24} n={score.checkpoints:>3}  "
        f"order_mae current={current_mae:>5.2f} outlook={outlook_mae:>5.2f}  "
        f"winner_hits current={score.current_winner_hits:>3} outlook={score.outlook_winner_hits:>3}  "
        f"win_score_brier={brier:.3f}  invalid_leader_gap={score.invalid_leader_gaps}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixtures", nargs="*", type=Path)
    args = parser.parse_args()
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    fixtures = args.fixtures or sorted(fixture_dir.glob("*_race.jsonl"))

    total = Score()
    for path in fixtures:
        score = evaluate(path)
        total.extend(score)
        print(_format(path.stem, score))
    print(_format("ALL", total))


if __name__ == "__main__":
    main()
