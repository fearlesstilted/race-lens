from datetime import datetime, timedelta
import json

import pandas as pd


def test_detect_launch_ms_uses_session_clock(monkeypatch):
    from racelens.positions import launch

    class Session:
        date = datetime(2021, 3, 28, 14, 0)
        session_start_time = timedelta(minutes=90)

    monkeypatch.setattr(
        launch,
        "detect_launch_date",
        lambda _: datetime(2021, 3, 28, 13, 15, 1),
    )

    assert launch.detect_launch_ms(Session()) == 2_701_000


def test_raw_positions_skip_non_finite_coordinates(tmp_path, monkeypatch):
    from racelens.positions import launch, track

    session_zero = pd.Timestamp("2026-07-28T12:00:00")

    class Session:
        date = session_zero
        session_start_time = pd.Timedelta(0)
        pos_data = {
            "1": pd.DataFrame({
                "Date": [session_zero + pd.Timedelta(seconds=i) for i in range(4)],
                "X": [1.0, float("nan"), float("inf"), 3.0],
                "Y": [2.0, 2.0, 2.0, float("-inf")],
            }),
        }

        @staticmethod
        def get_driver(_):
            return {"Abbreviation": "VER"}

    monkeypatch.setattr(track, "_load_session", lambda *_: Session())
    monkeypatch.setattr(launch, "detect_launch_ms", lambda _: 0)
    output = tmp_path / "positions.jsonl"

    assert track.export_raw_positions(2026, "Test", "R", output) == 1
    assert [json.loads(line) for line in output.read_text().splitlines()] == [{
        "driver": "VER", "t_ms": 0, "x": 1.0, "y": 2.0,
    }]
