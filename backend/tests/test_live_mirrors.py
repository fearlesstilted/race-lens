"""Live mirrors of the predictive replay endpoints: /api/live/forecast,
/win-prob, /battles, /simulate-pit.

Same pure functions as the replay endpoints, fed by _live.state_now() — these
tests seed `api._live` directly (LiveRunner._poll_once(), no async loop
needed) rather than going through /api/live/start, matching the pattern in
test_live_runner.py::test_live_stop_twice_does_not_crash.
"""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.live.runner import LiveRunner  # noqa: E402
from tests.test_replay import mini_race  # noqa: E402

LIVE_ENDPOINTS = [
    ("/api/live/forecast", {}),
    ("/api/live/win-prob", {}),
    ("/api/live/battles", {}),
    ("/api/live/simulate-pit", {"driver": "VER"}),
]


@pytest.fixture
def client():
    return TestClient(__import__("racelens.api", fromlist=["app"]).app)


def _seeded_runner() -> LiveRunner:
    runner = LiveRunner(lambda: mini_race(), poll_interval_s=60.0)
    runner._poll_once()
    return runner


@pytest.mark.parametrize("path,params", LIVE_ENDPOINTS)
def test_live_mirrors_404_without_session(client, path, params):
    import racelens.api as api

    assert api._live is None
    r = client.get(path, params=params)
    assert r.status_code == 404


def test_live_mirrors_404_when_runner_has_no_engine(client):
    """Runner exists but hasn't completed a poll yet — still 404, not 500."""
    import racelens.api as api

    original = api._live
    try:
        api._live = LiveRunner(lambda: [], poll_interval_s=60.0)
        assert api._live.engine is None
        for path, params in LIVE_ENDPOINTS:
            r = client.get(path, params=params)
            assert r.status_code == 404, f"{path} should 404 with no engine data"
    finally:
        api._live = original


def test_live_forecast_mirrors_replay_shape(client):
    import racelens.api as api

    original_live, original_sid = api._live, api._live_session_id
    try:
        api._live = _seeded_runner()
        api._live_session_id = "silverstone_2026_race"

        r = client.get("/api/live/forecast", params={"laps": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {
            "at_ms", "laps_ahead", "effective_laps", "model", "calibrated",
            "projected_order", "projected",
        }
        assert body["laps_ahead"] == 5
        assert isinstance(body["projected_order"], list)
        assert isinstance(body["projected"], dict)
    finally:
        api._live, api._live_session_id = original_live, original_sid


def test_live_win_prob_mirrors_replay_shape(client):
    import racelens.api as api

    original_live, original_sid = api._live, api._live_session_id
    try:
        api._live = _seeded_runner()
        api._live_session_id = "silverstone_2026_race"

        r = client.get("/api/live/win-prob")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {
            "at_ms", "laps_remaining", "model", "calibrated", "win_prob",
            "win_score", "leader", "top",
        }
        assert isinstance(body["win_prob"], dict)
        assert body["leader"] in body["win_prob"]
    finally:
        api._live, api._live_session_id = original_live, original_sid


def test_live_win_prob_works_without_session_id(client):
    """source=openf1 live sessions never set _live_session_id — must not 500."""
    import racelens.api as api

    original_live, original_sid = api._live, api._live_session_id
    try:
        api._live = _seeded_runner()
        api._live_session_id = None

        r = client.get("/api/live/win-prob")
        assert r.status_code == 200, r.text
    finally:
        api._live, api._live_session_id = original_live, original_sid


def test_live_battles_mirrors_replay_shape(client):
    import racelens.api as api

    original_live, original_sid = api._live, api._live_session_id
    try:
        api._live = _seeded_runner()
        api._live_session_id = "silverstone_2026_race"

        r = client.get("/api/live/battles")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {"at_ms", "battles"}
        assert isinstance(body["battles"], list)
    finally:
        api._live, api._live_session_id = original_live, original_sid


def test_live_simulate_pit_mirrors_replay_shape(client):
    import racelens.api as api

    original_live, original_sid = api._live, api._live_session_id
    try:
        api._live = _seeded_runner()
        api._live_session_id = "silverstone_2026_race"

        r = client.get("/api/live/simulate-pit", params={"driver": "LEC"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {"driver", "confidence", "evidence"}
        assert body["driver"] == "LEC"
        assert "pit_loss_s" in body["evidence"]
    finally:
        api._live, api._live_session_id = original_live, original_sid


def test_live_simulate_pit_works_without_session_id(client):
    import racelens.api as api

    original_live, original_sid = api._live, api._live_session_id
    try:
        api._live = _seeded_runner()
        api._live_session_id = None

        r = client.get("/api/live/simulate-pit", params={"driver": "LEC"})
        assert r.status_code == 200, r.text
    finally:
        api._live, api._live_session_id = original_live, original_sid
