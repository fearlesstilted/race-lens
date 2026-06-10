from racelens.insights.pit_window import detect_pit_window


def _state(rows: dict[str, tuple[float | None, int]]) -> dict:
    """rows: driver → (gap_to_leader_s, tyre_age_laps)"""
    return {
        "at_ms": 2_000_000,
        "lap": 30,
        "classification": list(rows),
        "drivers": {
            d: {"gap_s": g, "tyre_age_laps": age, "in_pit": False}
            for d, (g, age) in rows.items()
        },
    }


def test_leader_with_big_gap_has_open_window():
    s = _state({"LEC": (None, 20), "PIA": (25.0, 20), "SAI": (30.0, 20)})
    found = detect_pit_window(s)
    assert [i["driver_ids"] for i in found] == [["LEC"]]
    assert found[0]["evidence"]["margin_s"] == 5.0


def test_close_car_behind_keeps_window_shut():
    s = _state({"LEC": (None, 20), "PIA": (15.0, 20), "SAI": (40.0, 20)})
    assert [i["driver_ids"][0] for i in detect_pit_window(s)] == ["PIA"]  # 25s clear of SAI


def test_fresh_tyres_not_interesting():
    s = _state({"LEC": (None, 3), "PIA": (50.0, 3)})
    assert detect_pit_window(s) == []
