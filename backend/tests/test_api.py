import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.events.models import dump_jsonl  # noqa: E402

from tests.test_replay import mini_race  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "2024_mini_race.jsonl").write_text(dump_jsonl(mini_race()), encoding="utf-8")
    import racelens.api as api

    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()
    return TestClient(api.app)


def test_sessions_and_state(client):
    assert client.get("/api/sessions").json() == [{"session_id": "2024_mini_race"}]

    s = client.get("/api/sessions/2024_mini_race/state", params={"at_ms": 140_000}).json()
    assert s["classification"] == ["VER", "NOR", "LEC"]
    assert s["drivers"]["LEC"]["pit_count"] == 1

    assert client.get("/api/sessions/nope/state", params={"at_ms": 0}).status_code == 404


def test_insights_endpoint(client):
    r = client.get("/api/sessions/2024_mini_race/insights", params={"at_ms": 247_000}).json()
    assert r["insights"][0]["driver_ids"] == ["LEC", "NOR"]
    early = client.get("/api/sessions/2024_mini_race/insights", params={"at_ms": 100_000}).json()
    assert early["insights"] == []


def test_stream_simulated_live(client):
    chunks = []
    with client.stream(
        "GET",
        "/api/sessions/2024_mini_race/stream",
        params={"speed": 100_000, "from_ms": 245_000, "tick_ms": 2_000},
    ) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                chunks.append(line)
    # 245s, 247s, 249s + clamped final 250s = 4 states, then the end marker's data line
    assert len(chunks) == 5
    import json

    last_state = json.loads(chunks[3].removeprefix("data:"))
    assert last_state["session_status"] == "finished"
    assert last_state["active_insights"][0]["driver_ids"] == ["LEC", "NOR"]
    assert "commentary" in last_state
    assert len(last_state["commentary"]) == len(last_state["active_insights"])


def test_stream_speed_zero_returns_422(client):
    r = client.get(
        "/api/sessions/2024_mini_race/stream",
        params={"speed": 0, "tick_ms": 1000},
    )
    assert r.status_code == 422


def test_track_endpoint(tmp_path, monkeypatch):
    import json as _json
    import racelens.api as api

    track_data = {"session_id": "2024_mini_race", "viewbox": [600, 400], "points": [[10.0, 20.0], [30.0, 40.0]]}
    (tmp_path / "2024_mini_race.jsonl").write_text(
        dump_jsonl(mini_race()), encoding="utf-8"
    )
    (tmp_path / "2024_mini_race.track.json").write_text(
        _json.dumps(track_data), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()
    c = TestClient(api.app)

    r = c.get("/api/sessions/2024_mini_race/track")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "2024_mini_race"
    assert body["viewbox"] == [600, 400]
    assert len(body["points"]) == 2

    assert c.get("/api/sessions/nope/track").status_code == 404


def test_positions_endpoint(tmp_path, monkeypatch):
    import json as _json
    import racelens.api as api

    pos_data = {
        "session_id": "2024_mini_race",
        "start_ms": 0,
        "tick_ms": 500,
        "viewbox": [600, 400],
        "drivers": {"LEC": [[100.0, 200.0], None, [110.0, 205.0]]},
    }
    (tmp_path / "2024_mini_race.jsonl").write_text(
        dump_jsonl(mini_race()), encoding="utf-8"
    )
    (tmp_path / "2024_mini_race.positions.json").write_text(
        _json.dumps(pos_data), encoding="utf-8"
    )
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()
    c = TestClient(api.app)

    r = c.get("/api/sessions/2024_mini_race/positions")
    assert r.status_code == 200
    body = r.json()
    assert body["tick_ms"] == 500
    assert "LEC" in body["drivers"]
    assert body["drivers"]["LEC"][1] is None  # null frame preserved

    assert c.get("/api/sessions/nope/positions").status_code == 404


def test_timeline(client):
    t = client.get("/api/sessions/2024_mini_race/timeline").json()
    assert t["start_ms"] == 0
    assert t["end_ms"] == 250_000
    assert t["lap_marks"]["1"] == 80_000  # first lap-1 completion


# ── Replay download endpoint ───────────────────────────────────────────────────

def test_download_replay_writes_fixture_and_returns_shape(tmp_path, monkeypatch):
    """POST /api/replays/download writes fixture + returns {session_id, events, path}."""
    import urllib.error
    from unittest.mock import patch
    import racelens.api as api
    import racelens.adapters.openf1_adapter as _mod

    # Use tmp_path as fixture dir so the write is isolated
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()

    fake_events = mini_race()

    def mock_find_session(year, country, session_name="Race"):
        return 9999

    def mock_ingest(session_key):
        return fake_events

    c = TestClient(api.app)

    with (
        patch.object(_mod, "find_session", mock_find_session),
        patch("racelens.api.ingest_openf1", mock_ingest),
    ):
        r = c.post(
            "/api/replays/download",
            params={"year": 2024, "country": "Monaco", "session": "Race"},
        )

    assert r.status_code == 200, r.text
    body = r.json()

    # Response shape
    assert "session_id" in body
    assert "events" in body
    assert "path" in body
    assert body["events"] == len(fake_events)
    assert body["session_id"] == "monaco_2024_race"

    # Fixture file must have been written
    written = tmp_path / "monaco_2024_race.jsonl"
    assert written.is_file(), f"Expected fixture file at {written}"
    lines = [l for l in written.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == len(fake_events)


def test_download_replay_404_on_unknown_session(tmp_path, monkeypatch):
    """POST /api/replays/download with unknown session returns 404."""
    import racelens.adapters.openf1_adapter as _mod
    from unittest.mock import patch
    import racelens.api as api

    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()

    c = TestClient(api.app)

    def mock_find_fail(year, country, session_name="Race"):
        raise ValueError("No OpenF1 session found for year=2024, location='Atlantis'")

    with patch.object(_mod, "find_session", mock_find_fail):
        r = c.post(
            "/api/replays/download",
            params={"year": 2024, "country": "Atlantis", "session": "Race"},
        )

    assert r.status_code == 404
    assert "No OpenF1 session" in r.json()["detail"]


def test_download_replay_502_on_openf1_error(tmp_path, monkeypatch):
    """POST /api/replays/download returns 502 when OpenF1 is unreachable."""
    import urllib.error
    from unittest.mock import patch
    import racelens.api as api
    import racelens.adapters.openf1_adapter as _mod

    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()

    c = TestClient(api.app)

    def mock_find_session(year, country, session_name="Race"):
        return 9999

    def mock_ingest_fail(session_key):
        raise urllib.error.URLError("simulated network error")

    with (
        patch.object(_mod, "find_session", mock_find_session),
        patch("racelens.api.ingest_openf1", mock_ingest_fail),
    ):
        r = c.post(
            "/api/replays/download",
            params={"year": 2024, "country": "Monaco", "session": "Race"},
        )

    assert r.status_code == 502
    assert "unavailable" in r.json()["detail"].lower()
