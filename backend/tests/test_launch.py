from datetime import datetime, timedelta


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
