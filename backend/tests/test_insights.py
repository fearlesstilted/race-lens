from racelens.insights.traffic import detect_traffic_risk
from racelens.replay.engine import ReplayEngine

from tests.test_replay import mini_race


def test_traffic_risk_detected_at_finish():
    state = ReplayEngine(mini_race()).state_at(247_000)
    found = detect_traffic_risk(state)
    assert len(found) == 1
    ins = found[0]
    assert ins["type"] == "TRAFFIC_RISK_HIGH"          # LEC 2.8s/lap faster than NOR
    assert ins["driver_ids"] == ["LEC", "NOR"]
    assert ins["evidence"]["interval_s"] == 0.7
    assert ins["evidence"]["pace_delta_ms"] == 2_800


def test_no_traffic_risk_without_interval_data():
    state = ReplayEngine(mini_race()).state_at(140_000)
    assert detect_traffic_risk(state) == []


def test_insights_are_deterministic_and_spoiler_free():
    engine = ReplayEngine(mini_race())
    early = detect_traffic_risk(engine.state_at(100_000))
    assert early == []                                  # no future leakage into earlier laps
    assert detect_traffic_risk(engine.state_at(247_000)) == detect_traffic_risk(
        engine.state_at(247_000)
    )
