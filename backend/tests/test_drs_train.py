from racelens.insights.drs_train import detect_drs_train


def _state(intervals: dict[str, float | None], in_pit: set[str] = frozenset()) -> dict:
    order = list(intervals)
    return {
        "at_ms": 1_000_000,
        "lap": 10,
        "classification": order,
        "drivers": {
            d: {"interval_s": iv, "in_pit": d in in_pit}
            for d, iv in intervals.items()
        },
    }


def test_chain_of_four_detected():
    s = _state({"VER": None, "LEC": 0.5, "NOR": 0.8, "PIA": 0.9, "HAM": 4.0})
    trains = detect_drs_train(s)
    assert len(trains) == 1
    assert trains[0]["driver_ids"] == ["VER", "LEC", "NOR", "PIA"]
    assert trains[0]["evidence"]["cars"] == 4
    assert trains[0]["severity"] == "medium"


def test_two_cars_is_not_a_train():
    s = _state({"VER": None, "LEC": 0.5, "NOR": 3.0})
    assert detect_drs_train(s) == []


def test_pit_breaks_the_chain():
    s = _state({"VER": None, "LEC": 0.5, "NOR": 0.8, "PIA": 0.9}, in_pit={"NOR"})
    assert detect_drs_train(s) == []


def test_five_plus_cars_is_high_severity():
    s = _state({"A": None, "B": 0.3, "C": 0.4, "D": 0.5, "E": 0.6, "F": 0.7})
    trains = detect_drs_train(s)
    assert trains[0]["severity"] == "high"
    assert trains[0]["evidence"]["head"] == "A"


def test_lap_1_suppressed():
    s = _state({"VER": None, "LEC": 0.5, "NOR": 0.8, "PIA": 0.9})
    s["lap"] = 1
    assert detect_drs_train(s) == []


def test_lap_2_suppressed():
    s = _state({"VER": None, "LEC": 0.5, "NOR": 0.8, "PIA": 0.9})
    s["lap"] = 2
    assert detect_drs_train(s) == []


def test_large_peloton_suppressed():
    """9+ car chain is SC/race-start compression, not a DRS train — must not emit."""
    drivers = {chr(65 + i): (0.4 if i > 0 else None) for i in range(9)}
    s = _state(drivers)
    assert detect_drs_train(s) == []
