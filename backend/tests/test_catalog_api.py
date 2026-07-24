from datetime import UTC, datetime
import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.events.models import dump_jsonl  # noqa: E402
from racelens.preparations import PreparationQueue, QueueFullError  # noqa: E402
from racelens.recorder.schedule import ScheduledSession  # noqa: E402
from tests.test_replay import mini_race  # noqa: E402


def test_preparation_queue_is_atomic_bounded_and_idempotent(tmp_path):
    queue = PreparationQueue(tmp_path / "queue", max_jobs=1)
    first, created = queue.enqueue("2024-08-fp1", "monaco_2024_fp1")
    duplicate, created_again = queue.enqueue("2024-08-fp1", "monaco_2024_fp1")

    assert created is True
    assert created_again is False
    assert duplicate == first
    assert queue.get("2024-08-fp1") == first
    with pytest.raises(QueueFullError):
        queue.enqueue("2024-08-q", "monaco_2024_qualifying")
    assert sorted(path.name for path in (tmp_path / "queue").glob("*.json")) == [
        "2024-08-fp1.json",
    ]
    queue.finish("2024-08-fp1", error="upstream unavailable")
    retried, retried_now = queue.enqueue("2024-08-fp1", "monaco_2024_fp1")
    assert retried_now is True
    assert retried["status"] == "queued"
    assert retried["error"] is None


def test_catalog_matches_legacy_venue_fixture_names(tmp_path, monkeypatch):
    import racelens.catalog as catalog

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for name in ("spain_2024_race", "silverstone_2024_race"):
        (fixtures / f"{name}.jsonl").write_text("{}\n", encoding="utf-8")
    sessions = [
        ScheduledSession(2024, 10, "Spanish Grand Prix", "R", datetime(2024, 6, 23, 13, tzinfo=UTC)),
        ScheduledSession(2024, 12, "British Grand Prix", "R", datetime(2024, 7, 7, 14, tzinfo=UTC)),
    ]
    monkeypatch.setattr(catalog, "load_fastf1_schedule", lambda year: sessions)

    catalog.build_catalog(
        2024,
        fixtures,
        PreparationQueue(tmp_path / "queue"),
        tmp_path / "cache",
        preparation_enabled=False,
    )
    monkeypatch.setattr(
        catalog,
        "load_fastf1_schedule",
        lambda year: (_ for _ in ()).throw(ModuleNotFoundError()),
    )
    monkeypatch.setattr(
        catalog,
        "load_jolpica_schedule",
        lambda year, cache_dir: (_ for _ in ()).throw(catalog.CatalogUnavailable()),
    )
    body = catalog.build_catalog(
        2024,
        fixtures,
        PreparationQueue(tmp_path / "queue"),
        tmp_path / "cache",
        preparation_enabled=False,
    )
    by_id = {
        item["session_id"]: item
        for event in body["events"]
        for item in event["sessions"]
    }
    assert by_id["2024-10-r"]["replay_session_id"] == "spain_2024_race"
    assert by_id["2024-12-r"]["replay_session_id"] == "silverstone_2024_race"


def test_jolpica_fallback_uses_fixed_host_and_disk_cache(tmp_path, monkeypatch):
    import racelens.catalog as catalog

    payload = {
        "MRData": {"RaceTable": {"Races": [{
            "round": "8",
            "raceName": "Monaco Grand Prix",
            "date": "2024-05-26",
            "time": "13:00:00Z",
            "FirstPractice": {"date": "2024-05-24", "time": "11:30:00Z"},
            "SprintQualifying": {"date": "2024-05-24", "time": "15:30:00Z"},
            "Qualifying": {"date": "2024-05-25", "time": "14:00:00Z"},
        }]}}
    }
    called = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return json.dumps(payload).encode()

    def urlopen(request, timeout):
        called.update(url=request.full_url, timeout=timeout)
        return Response()

    monkeypatch.setattr(catalog.urllib.request, "urlopen", urlopen)
    sessions = catalog.load_jolpica_schedule(2024, tmp_path / "cache")
    assert called == {"url": "https://api.jolpi.ca/ergast/f1/2024.json", "timeout": 5}
    assert [item.kind for item in sessions] == ["FP1", "SQ", "Q", "R"]

    monkeypatch.setattr(
        catalog.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("fresh disk cache should avoid the network"),
    )
    assert catalog.load_jolpica_schedule(2024, tmp_path / "cache") == sessions


def test_catalog_prepare_is_whitelisted_bounded_and_idempotent(tmp_path, monkeypatch):
    import racelens.api as api
    import racelens.catalog as catalog

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "monaco_2024_race.jsonl").write_text(
        dump_jsonl(mini_race()), encoding="utf-8",
    )
    for name in ("spain_2024_race", "silverstone_2024_race"):
        (fixtures / f"{name}.jsonl").write_text(dump_jsonl(mini_race()), encoding="utf-8")
    sessions = [
        ScheduledSession(2024, 8, "Monaco Grand Prix", "FP1", datetime(2024, 5, 24, 11, tzinfo=UTC)),
        ScheduledSession(2024, 8, "Monaco Grand Prix", "Q", datetime(2024, 5, 25, 14, tzinfo=UTC)),
        ScheduledSession(2024, 8, "Monaco Grand Prix", "R", datetime(2024, 5, 26, 13, tzinfo=UTC)),
        ScheduledSession(2024, 10, "Spanish Grand Prix", "R", datetime(2024, 6, 23, 13, tzinfo=UTC)),
        ScheduledSession(2024, 12, "British Grand Prix", "R", datetime(2024, 7, 7, 14, tzinfo=UTC)),
    ]
    monkeypatch.setattr(catalog, "load_schedule", lambda year, cache_dir: sessions)
    monkeypatch.setattr(api, "FIXTURES_DIR", fixtures)
    monkeypatch.setattr(api, "CATALOG_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(api, "PREPARATION_QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(api, "PREPARATION_QUEUE_MAX", 1)
    monkeypatch.setattr(api, "READONLY", False)
    client = TestClient(api.app)

    response = client.get("/api/catalog", params={"season": 2024})
    assert response.status_code == 200
    body = response.json()
    assert body["catalog_available"] is True
    assert body["preparation_enabled"] is True
    by_id = {
        item["session_id"]: item
        for event in body["events"]
        for item in event["sessions"]
    }
    assert by_id["2024-08-r"]["status"] == "ready"
    assert by_id["2024-08-r"]["replay_session_id"] == "monaco_2024_race"
    assert by_id["2024-08-fp1"]["status"] == "prepare"
    assert by_id["2024-10-r"]["replay_session_id"] == "spain_2024_race"
    assert by_id["2024-12-r"]["replay_session_id"] == "silverstone_2024_race"

    first = client.post("/api/catalog/2024-08-fp1/prepare")
    second = client.post("/api/catalog/2024-08-fp1/prepare")
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert first.headers["location"] == "/api/preparations/2024-08-fp1"
    assert client.get("/api/preparations/2024-08-fp1").json() == first.json()
    assert len(list((tmp_path / "queue").glob("*.json"))) == 1

    assert client.post("/api/catalog/2024-08-q/prepare").status_code == 429
    assert client.post("/api/catalog/2024-99-r/prepare").status_code == 404
    assert not (tmp_path / "queue" / "2024-99-r.json").exists()


def test_catalog_prepare_is_explicitly_disabled_in_readonly_mode(tmp_path, monkeypatch):
    import racelens.api as api
    import racelens.catalog as catalog

    session = ScheduledSession(
        2024, 8, "Monaco Grand Prix", "FP1", datetime(2024, 5, 24, 11, tzinfo=UTC),
    )
    monkeypatch.setattr(catalog, "load_schedule", lambda year, cache_dir: [session])
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(api, "PREPARATION_QUEUE_DIR", tmp_path / "queue")
    monkeypatch.setattr(api, "READONLY", True)
    client = TestClient(api.app)

    assert client.get("/api/catalog", params={"season": 2024}).json()["preparation_enabled"] is False
    response = client.post("/api/catalog/2024-08-fp1/prepare")
    assert response.status_code == 403
    assert "read-only" in response.json()["detail"]
    assert client.get("/api/capabilities").json()["preparation_enabled"] is False
