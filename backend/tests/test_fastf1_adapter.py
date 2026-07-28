from datetime import timedelta

from racelens.adapters._common import fastf1_lap1_start
from racelens.adapters.fastf1_adapter import best_lap_position_events
from racelens.replay.engine import ReplayEngine


class _Series(list):
    def dropna(self):
        return _Series(value for value in self if value is not None)

    def min(self):
        return min(self)

    def __sub__(self, other):
        return _Series(
            left - right if left is not None and right is not None else None
            for left, right in zip(self, other)
        )


def test_lap1_start_uses_explicit_time_when_lap_time_is_missing():
    lap1 = {
        "LapStartTime": _Series([timedelta(seconds=42), timedelta(seconds=43)]),
        "Time": _Series([timedelta(seconds=130), timedelta(seconds=131)]),
        "LapTime": _Series([None, None]),
    }

    assert fastf1_lap1_start(lap1) == timedelta(seconds=42)


def test_lap1_start_falls_back_for_legacy_fastf1_data():
    lap1 = {
        "Time": _Series([timedelta(seconds=130), timedelta(seconds=131)]),
        "LapTime": _Series([timedelta(seconds=90), None]),
    }

    assert fastf1_lap1_start(lap1) == timedelta(seconds=40)


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
