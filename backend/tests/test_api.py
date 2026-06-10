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


def test_timeline(client):
    t = client.get("/api/sessions/2024_mini_race/timeline").json()
    assert t["start_ms"] == 0
    assert t["end_ms"] == 250_000
    assert t["lap_marks"]["1"] == 80_000  # first lap-1 completion
