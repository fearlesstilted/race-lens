from racelens.adapters.fastf1_adapter import best_lap_position_events
from racelens.replay.engine import ReplayEngine


def test_practice_positions_follow_each_drivers_best_lap():
    events = best_lap_position_events(
        "practice",
        [
            (100, "VER", 90_000),
            (110, "ANT", 89_000),
            (120, "VER", 88_000),
            (130, "ANT", 91_000),
        ],
    )

    state = ReplayEngine(events).state_at(130)
    assert state["classification"] == ["VER", "ANT"]
