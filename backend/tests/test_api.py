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
