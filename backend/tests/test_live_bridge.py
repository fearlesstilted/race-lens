import copy
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import racelens.object_storage as storage  # noqa: E402
from racelens.object_storage import StorageError, publish_session  # noqa: E402
from racelens.recorder.schedule import ScheduledSession  # noqa: E402
from racelens.recorder.worker import Config, Recorder, fixture_stem  # noqa: E402
from tests.test_object_storage import MemoryStore  # noqa: E402


NOW = datetime(2026, 8, 23, 13, 5, tzinfo=UTC)
SESSION = ScheduledSession(2026, 15, "Dutch Grand Prix", "R", NOW - timedelta(minutes=5))


def _config(tmp_path):
    return Config(
        state_dir=tmp_path / "state",
        raw_dir=tmp_path / "raw",
        data_dir=tmp_path / "data",
        interval_seconds=120,
        capture_poll_seconds=5,
        raw_retention_days=14,
        publish_sessions=frozenset({"R"}),
        transcribe_radio=True,
        race_core=tmp_path / "race-core",
        git_publication=False,
    )


def _line(category, payload, timestamp=""):
    return repr([category, payload, timestamp])


def _feed_prefix():
    info = {
        "Meeting": {
            "Key": 15,
            "Number": 15,
            "Name": "Dutch Grand Prix",
            "Location": "Zandvoort",
        },
        "Key": 99,
        "Name": "Race",
        "StartDate": "2026-08-23T13:00:00Z",
        "Path": "2026/Dutch/Race/",
    }
    return [
        _line("SessionInfo", json.dumps(info)),
        _line(
            "SessionData",
            {"StatusSeries": [{"SessionStatus": "Started", "Utc": "2026-08-23T13:00:00Z"}]},
        ),
        _line("DriverList", {"1": {"Tla": "VER"}, "4": {"Tla": "NOR"}}),
        _line("SessionStatus", {"Status": "Started"}, "2026-08-23T13:00:00Z"),
        _line(
            "TimingData",
            {"Lines": {"1": {"Position": "1"}, "4": {"Position": "2", "GapToLeader": "+1.0"}}},
            "2026-08-23T13:00:01Z",
        ),
    ]


def _write_feed(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))


def _valid_records(now=NOW):
    canonical = SESSION.session_id
    replay = fixture_stem(SESSION)
    generated = now.isoformat().replace("+00:00", "Z")
    expires = (now + timedelta(seconds=20)).isoformat().replace("+00:00", "Z")
    key = f"live/{canonical}/snapshot.json"
    pointer = {
        "schema_version": 1,
        "canonical_session_id": canonical,
        "replay_session_id": replay,
        "status": "live",
        "snapshot_key": key,
        "created_at": generated,
        "updated_at": generated,
        "failure": None,
    }
    state = {
        "session_id": replay,
        "at_ms": 1_000,
        "lap": 1,
        "session_status": "started",
        "session_name": "ZANDVOORT · RACE",
        "status_since_ms": 0,
        "total_laps": 72,
        "classification": ["VER"],
        "drivers": {"VER": {"position": 1, "rank": 1}},
        "data_quality": {"status": "good"},
        "frame_source": "live",
        "viewbox": None,
    }
    snapshot = {
        "schema_version": 1,
        "canonical_session_id": canonical,
        "replay_session_id": replay,
        "sequence": 1,
        "generated_at": generated,
        "expires_at": expires,
        "race_state": state,
        "battles": [],
        "active_insights": [],
        "recent_passes": [],
        "feed": {"en": [], "ru": []},
        "commentary": {
            "en": {"beginner": [], "pro": []},
            "ru": {"beginner": [], "pro": []},
        },
        "radio": [],
        "capture_freshness": {
            "raw_size": 100,
            "raw_updated_at": generated,
            "seconds_since_growth": 0.0,
            "transport_growing": True,
        },
        "data_quality": "good",
    }
    return pointer, snapshot


def test_live_records_reject_invalid_oversized_stale_and_mismatched_data():
    store = MemoryStore()
    pointer, snapshot = _valid_records()
    storage.write_live_snapshot(store, pointer, snapshot, now=NOW)
    assert storage.load_live(store, now=NOW)["snapshot"]["sequence"] == 1

    bad_pointer = {**pointer, "status": "starting"}
    with pytest.raises(storage.LiveRecordError):
        storage.validate_live_pointer(bad_pointer)

    oversized = copy.deepcopy(snapshot)
    oversized["race_state"]["padding"] = "x" * storage.MAX_LIVE_SNAPSHOT_BYTES
    with pytest.raises(storage.LiveRecordError, match="size"):
        storage.validate_live_snapshot(oversized, pointer=pointer, now=NOW)

    stale = copy.deepcopy(snapshot)
    stale["generated_at"] = (NOW - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    stale["expires_at"] = (NOW - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    with pytest.raises(storage.LiveRecordError, match="stale"):
        storage.validate_live_snapshot(stale, pointer=pointer, now=NOW)

    mismatched = copy.deepcopy(snapshot)
    mismatched["replay_session_id"] = "other_2026_race"
    with pytest.raises(storage.LiveRecordError, match="identity"):
        storage.validate_live_snapshot(mismatched, pointer=pointer, now=NOW)


def test_recorder_snapshot_handles_partial_append_sc_vsc_and_late_transcript(tmp_path):
    store = MemoryStore()
    recorder = Recorder(_config(tmp_path), now=lambda: NOW, object_store=store)
    feed = recorder._paths(SESSION)["raw"]
    wrong = _feed_prefix()
    wrong[0] = wrong[0].replace("Dutch Grand Prix", "Belgian Grand Prix")
    _write_feed(feed, wrong)
    assert not recorder._publish_live_snapshot(SESSION, feed)
    assert "live/current.json" not in store.objects

    lines = _feed_prefix() + [
        _line(
            "RaceControlMessages",
            {"Messages": [{"Utc": "2026-08-23T13:01:00Z", "Category": "Flag", "Message": "SAFETY CAR DEPLOYED"}]},
            "2026-08-23T13:01:00Z",
        ),
        _line(
            "TeamRadio",
            {"Captures": [{"Utc": "2026-08-23T13:01:01Z", "RacingNumber": "1", "Path": "TeamRadio/ver.mp3"}]},
            "2026-08-23T13:01:01Z",
        ),
    ]
    _write_feed(feed, lines)
    with feed.open("a", encoding="utf-8") as handle:
        handle.write("['TimingData', {'Lines':")

    class Transcripts:
        calls = 0

        def get(self, _url):
            self.calls += 1
            return "box now" if self.calls > 1 else None

    recorder._transcripts = Transcripts()
    assert recorder._publish_live_snapshot(SESSION, feed)
    first = store.objects[f"live/{SESSION.session_id}/snapshot.json"]
    assert first["race_state"]["session_status"] == "safety_car"
    assert first["radio"][0]["audio_url"].startswith("https://")
    assert first["radio"][0]["transcript"] is None

    with feed.open("a", encoding="utf-8") as handle:
        handle.write(" {'1': {'Position': '1'}}}, '2026-08-23T13:01:02Z']\n")
        handle.write(_line(
            "RaceControlMessages",
            {"Messages": [{"Utc": "2026-08-23T13:01:03Z", "Category": "Flag", "Message": "VIRTUAL SAFETY CAR DEPLOYED"}]},
            "2026-08-23T13:01:03Z",
        ) + "\n")
    os.utime(feed, (NOW.timestamp(), NOW.timestamp()))

    assert recorder._publish_live_snapshot(SESSION, feed)
    second = store.objects[f"live/{SESSION.session_id}/snapshot.json"]
    assert second["sequence"] > first["sequence"]
    assert second["race_state"]["session_status"] == "vsc"
    assert second["radio"][0]["transcript"] == "box now"


def test_capture_quality_uses_transport_growth_not_modeled_events(tmp_path):
    recorder = Recorder(_config(tmp_path), now=lambda: NOW, object_store=MemoryStore())
    feed = recorder._paths(SESSION)["raw"]
    _write_feed(feed, _feed_prefix())

    first = recorder._capture_freshness(SESSION, feed)
    with feed.open("a", encoding="utf-8") as handle:
        handle.write("ignored transport heartbeat\n")
    os.utime(feed, ((NOW + timedelta(seconds=10)).timestamp(),) * 2)
    recorder.now = lambda: NOW + timedelta(seconds=10)
    growing = recorder._capture_freshness(SESSION, feed)
    recorder.now = lambda: NOW + timedelta(seconds=31)
    frozen = recorder._capture_freshness(SESSION, feed)

    assert first["data_quality"] == "good"
    assert growing["data_quality"] == "good"
    assert growing["capture_freshness"]["transport_growing"] is True
    assert frozen["data_quality"] == "stalled"
    assert frozen["capture_freshness"]["transport_growing"] is False


def test_finishing_then_verified_ready_or_safe_failed_keeps_snapshot(tmp_path):
    store = MemoryStore()
    recorder = Recorder(_config(tmp_path), now=lambda: NOW, object_store=store)
    feed = recorder._paths(SESSION)["raw"]
    _write_feed(feed, _feed_prefix())
    assert recorder._publish_live_snapshot(SESSION, feed)
    snapshot_key = f"live/{SESSION.session_id}/snapshot.json"
    snapshot = copy.deepcopy(store.objects[snapshot_key])

    recorder._set_live_status(SESSION, "finishing")
    assert store.objects["live/current.json"]["status"] == "finishing"
    with pytest.raises(storage.LiveRecordError, match="manifest"):
        recorder._set_live_status(SESSION, "replay_ready")

    archive = tmp_path / "archive"
    archive.mkdir()
    replay = fixture_stem(SESSION)
    files = []
    for suffix in (".jsonl", ".track.json", ".positions.json"):
        path = archive / f"{replay}{suffix}"
        path.write_text("{}\n", encoding="utf-8")
        files.append(path)
    publish_session(store, SESSION.session_id, replay, *files, event_count=1)
    recorder._set_live_status(SESSION, "replay_ready")
    assert store.objects["live/current.json"]["status"] == "replay_ready"

    recorder._set_live_status(SESSION, "failed", failure="Archive preparation failed")
    pointer = store.objects["live/current.json"]
    assert pointer["status"] == "failed"
    assert pointer["failure"] == "Archive preparation failed"
    assert store.objects[snapshot_key] == snapshot


def test_remote_live_api_fallback_cache_and_sanitized_storage_failure(monkeypatch):
    import racelens.api as api

    class CountingStore(MemoryStore):
        reads = 0

        def get_json(self, key, *, limit):
            self.reads += 1
            return super().get_json(key, limit=limit)

    store = CountingStore()
    pointer, snapshot = _valid_records()
    storage.write_live_snapshot(store, pointer, snapshot, now=NOW)
    monkeypatch.setattr(api, "_object_store", lambda: store)
    monkeypatch.setattr(api, "_live", None)
    monkeypatch.setattr(api, "_remote_live_cache", None)
    monkeypatch.setattr(api, "_utcnow", lambda: NOW)
    client = TestClient(api.app)

    status = client.get("/api/live/status")
    assert status.status_code == 200
    assert status.json()["status"] == "live"
    assert client.get("/api/live/feed").json() == []
    assert client.get("/api/live/battles").json() == {"at_ms": 1000, "battles": []}
    assert client.get("/api/live/forecast").status_code == 200
    pit = client.get("/api/live/simulate-pit", params={"driver": "VER"})
    assert pit.status_code == 200 and pit.json()["driver"] == "VER"
    assert store.reads == 2

    storage.write_live_status(
        store, SESSION.session_id, fixture_stem(SESSION), "finishing", now=NOW,
    )
    monkeypatch.setattr(api, "_remote_live_cache", None)
    with client.stream("GET", "/api/live/stream", params={"tick_s": 0.5}) as response:
        assert "event: end" in next(response.iter_text())
    monkeypatch.setattr(api, "READONLY", True)
    assert client.post(
        "/api/live/start", params={"year": 2026, "country": "Zandvoort"},
    ).status_code == 403
    assert client.post("/api/live/stop").status_code == 403

    class BrokenStore:
        def get_json(self, *_args, **_kwargs):
            raise StorageError("secret endpoint and bucket")

    monkeypatch.setattr(api, "_object_store", lambda: BrokenStore())
    monkeypatch.setattr(api, "_remote_live_cache", None)
    failed = client.get("/api/live/status")
    assert failed.status_code == 503
    assert "secret" not in failed.text
