import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.events.models import dump_jsonl  # noqa: E402
from racelens.object_storage import RemoteSessionCache, publish_session  # noqa: E402
from tests.test_object_storage import MemoryStore  # noqa: E402
from tests.test_replay import mini_race  # noqa: E402


def test_remote_api_reads_survive_forced_eviction(tmp_path, monkeypatch):
    import racelens.api as api

    store = MemoryStore()
    sizes = []
    for replay_id in ("alpha_2024_race", "beta_2024_race"):
        fixture = tmp_path / f"{replay_id}.jsonl"
        track = tmp_path / f"{replay_id}.track.json"
        positions = tmp_path / f"{replay_id}.positions.json"
        fixture.write_text(dump_jsonl(mini_race()), encoding="utf-8")
        track.write_text(json.dumps({"session_id": replay_id, "points": [[0, 0]]}))
        positions.write_text(json.dumps({
            "session_id": replay_id,
            "start_ms": 0,
            "tick_ms": 1000,
            "drivers": {},
        }))
        publish_session(
            store, "2024-08-r", replay_id, fixture, track, positions,
            event_count=len(mini_race()),
        )
        sizes.append(sum(path.stat().st_size for path in (fixture, track, positions)))

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    cache = RemoteSessionCache(store, tmp_path / "cache")
    cache.max_bytes = max(sizes) + 100
    monkeypatch.setattr(api, "FIXTURES_DIR", fixtures)
    monkeypatch.setattr(api, "_remote_cache", lambda: cache)
    api._engine_cached.cache_clear()
    api._positions_data_cached.cache_clear()

    def read(replay_id):
        client = TestClient(api.app)
        return [
            client.get(f"/api/sessions/{replay_id}/state", params={"at_ms": 0}).status_code,
            client.get(f"/api/sessions/{replay_id}/track").status_code,
            client.get(f"/api/sessions/{replay_id}/positions").status_code,
            client.get(f"/api/sessions/{replay_id}/timeline").status_code,
        ]

    assert read("alpha_2024_race") == [200] * 4
    assert read("beta_2024_race") == [200] * 4
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(read, ("alpha_2024_race", "beta_2024_race")))
    assert results == [[200] * 4, [200] * 4]


def test_diagnostics_are_operational_and_sanitized(tmp_path, monkeypatch):
    import racelens.api as api

    class Cache:
        def stats(self):
            return {
                "materializations": 2,
                "hits": 3,
                "evictions": 1,
                "bytes": 456,
                "disk_bytes": 123,
                "max_bytes": 789,
            }

    class Live:
        def status(self):
            return {"data_quality": "good", "last_error": "SECRET_ACCESS_KEY=hidden"}

    monkeypatch.setenv("RACELENS_REVISION", "abc1234")
    monkeypatch.setattr(api, "STORAGE_CONFIG", SimpleNamespace(
        bucket="private-bucket", secret_access_key="SECRET_ACCESS_KEY=hidden",
    ))
    monkeypatch.setattr(api, "REMOTE_CACHE_DIR", tmp_path / "private-bucket")
    monkeypatch.setattr(api, "_remote_cache", lambda: Cache())
    monkeypatch.setattr(api, "_live", Live())
    monkeypatch.setattr(api, "_capture", object())

    response = TestClient(api.app).get("/api/diagnostics")
    body = response.json()

    assert response.status_code == 200
    assert body["revision"] == "abc1234"
    assert body["parsed_cache"]["engine"]["max_size"] == 1
    assert body["parsed_cache"]["positions"]["max_size"] == 1
    assert body["remote_cache"] == {
        "materializations": 2,
        "hits": 3,
        "evictions": 1,
        "bytes": 456,
        "disk_bytes": 123,
        "max_bytes": 789,
    }
    assert body["live"] == {"source": "signalr", "freshness": "fresh"}
    encoded = json.dumps(body)
    assert "SECRET_ACCESS_KEY" not in encoded
    assert "private-bucket" not in encoded
    assert str(tmp_path) not in encoded
