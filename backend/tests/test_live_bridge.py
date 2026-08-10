import copy
import asyncio
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
        "drivers": {"VER": {
            "position": 1,
            "rank": 1,
            "grid_position": 1,
            "laps_completed": 1,
            "last_lap_ms": 80_000,
            "best_lap_ms": 80_000,
            "gap_s": 0.0,
            "interval_s": None,
            "tyre_compound": "Medium",
            "tyre_age_laps": 1,
            "pit_count": 0,
            "in_pit": False,
            "recent_laps_ms": [80_000],
            "retired": False,
            "x": None,
            "y": None,
            "progress": None,
        }},
        "data_quality": {
            "status": "good",
            "last_event_ms": 1_000,
            "events_applied": 2,
            "duplicates_dropped": 0,
        },
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


def test_live_records_reject_inner_identity_malformed_values_and_path_text():
    pointer, snapshot = _valid_records()
    inner = copy.deepcopy(snapshot)
    inner["race_state"]["session_id"] = "other_2026_race"
    with pytest.raises(storage.LiveRecordError, match="identity"):
        storage.validate_live_snapshot(inner, pointer=pointer, now=NOW)

    malformed_pointer = {**pointer, "status": []}
    with pytest.raises(storage.LiveRecordError):
        storage.validate_live_pointer(malformed_pointer)
    malformed_snapshot = copy.deepcopy(snapshot)
    malformed_snapshot["data_quality"] = []
    with pytest.raises(storage.LiveRecordError):
        storage.validate_live_snapshot(malformed_snapshot, pointer=pointer, now=NOW)

    leaked = copy.deepcopy(snapshot)
    leaked["feed"]["en"] = [{
        "id": "leak",
        "at_ms": 1_000,
        "lap": 1,
        "kind": "RaceControlMessage",
        "tag": "FLAG",
        "text": "/home/recorder/.aws/credentials",
        "driver_id": None,
    }]
    with pytest.raises(storage.LiveRecordError, match="feed"):
        storage.validate_live_snapshot(leaked, pointer=pointer, now=NOW)
    with pytest.raises(storage.LiveRecordError):
        storage.validate_live_pointer({**pointer, "status": "failed", "failure": "S3 bucket secret"})

    missing = copy.deepcopy(snapshot)
    del missing["race_state"]["classification"]
    with pytest.raises(storage.LiveRecordError, match="race state"):
        storage.validate_live_snapshot(missing, pointer=pointer, now=NOW)


def test_live_records_accept_multiline_whisper_and_nullable_undercut_evidence():
    pointer, snapshot = _valid_records()
    transcript = "Brake balance endpoint\nput the tyres in the bucket"
    audio_url = "https://livetiming.formula1.com/static/2026/Dutch/Race/radio.mp3"
    radio_feed = {
        "id": "radio:ver",
        "at_ms": 1_000,
        "lap": 1,
        "kind": "RaceControlMessage",
        "tag": "FLAG",
        "text": "RADIO: VER",
        "driver_id": "VER",
        "audio_url": audio_url,
        "transcript": transcript,
    }
    snapshot["feed"] = {"en": [radio_feed], "ru": [copy.deepcopy(radio_feed)]}
    snapshot["radio"] = [{
        "audio_url": audio_url,
        "transcript": transcript,
        "driver_id": "VER",
        "at_ms": 1_000,
    }]
    snapshot["active_insights"] = [{
        "insight_id": "undercut:VER:1000",
        "type": "UNDERCUT_RISK_MEDIUM",
        "severity": "medium",
        "confidence": "medium",
        "created_at_ms": 1_000,
        "lap": 1,
        "driver_ids": ["VER", "NOR"],
        "evidence": {
            "interval_s": 1.5,
            "attacker_tyre_age_laps": 10,
            "defender_tyre_age_laps": None,
            "pace_delta_ms": 100,
        },
    }]

    assert storage.validate_live_snapshot(snapshot, pointer=pointer, now=NOW) == snapshot


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

    with pytest.raises(storage.LiveRecordError, match="transition"):
        recorder._set_live_status(SESSION, "failed", failure="Archive preparation failed")
    assert store.objects["live/current.json"]["status"] == "replay_ready"
    assert store.objects[snapshot_key] == snapshot


def test_live_status_enforces_lifecycle_graph_and_verified_retry(tmp_path):
    store = MemoryStore()
    pointer, snapshot = _valid_records()
    storage.write_live_snapshot(store, pointer, snapshot, now=NOW)
    with pytest.raises(storage.LiveRecordError, match="transition"):
        storage.write_live_status(
            store, SESSION.session_id, fixture_stem(SESSION), "replay_ready", now=NOW,
        )
    storage.write_live_status(
        store, SESSION.session_id, fixture_stem(SESSION), "failed",
        failure="Archive preparation failed", now=NOW,
    )
    with pytest.raises(storage.LiveRecordError, match="manifest"):
        storage.write_live_status(
            store, SESSION.session_id, fixture_stem(SESSION), "replay_ready", now=NOW,
        )

    archive = tmp_path / "retry"
    archive.mkdir()
    replay = fixture_stem(SESSION)
    files = []
    for suffix in (".jsonl", ".track.json", ".positions.json"):
        path = archive / f"{replay}{suffix}"
        path.write_text("{}\n", encoding="utf-8")
        files.append(path)
    publish_session(store, SESSION.session_id, replay, *files, event_count=1)
    storage.write_live_status(
        store, SESSION.session_id, replay, "replay_ready", now=NOW,
    )
    with pytest.raises(storage.LiveRecordError, match="transition"):
        storage.write_live_status(
            store, SESSION.session_id, replay, "finishing", now=NOW,
        )


def test_live_snapshot_preserves_created_at_for_same_identity_and_resets_for_new_race():
    store = MemoryStore()
    pointer, snapshot = _valid_records()
    storage.write_live_snapshot(store, pointer, snapshot, now=NOW)

    later = NOW + timedelta(seconds=5)
    next_pointer = {
        **pointer,
        "created_at": later.isoformat().replace("+00:00", "Z"),
        "updated_at": later.isoformat().replace("+00:00", "Z"),
    }
    next_snapshot = copy.deepcopy(snapshot)
    next_snapshot.update(
        sequence=2,
        generated_at=later.isoformat().replace("+00:00", "Z"),
        expires_at=(later + timedelta(seconds=20)).isoformat().replace("+00:00", "Z"),
    )
    storage.write_live_snapshot(store, next_pointer, next_snapshot, now=later)
    assert store.objects["live/current.json"]["created_at"] == pointer["created_at"]

    new_pointer = copy.deepcopy(next_pointer)
    new_pointer.update(
        canonical_session_id="2026-16-r",
        replay_session_id="italian_2026_race",
        snapshot_key="live/2026-16-r/snapshot.json",
    )
    new_snapshot = copy.deepcopy(next_snapshot)
    new_snapshot.update(
        canonical_session_id="2026-16-r",
        replay_session_id="italian_2026_race",
    )
    new_snapshot["race_state"]["session_id"] = "italian_2026_race"
    storage.write_live_snapshot(store, new_pointer, new_snapshot, now=later)
    assert store.objects["live/current.json"]["created_at"] == next_pointer["created_at"]


def test_live_snapshot_writer_cannot_publish_ready_or_overwrite_terminal_state():
    pointer, snapshot = _valid_records()
    store = MemoryStore()
    with pytest.raises(storage.LiveRecordError, match="snapshot pointer"):
        storage.write_live_snapshot(
            store, {**pointer, "status": "replay_ready"}, snapshot, now=NOW,
        )
    assert "live/current.json" not in store.objects

    storage.write_live_snapshot(store, pointer, snapshot, now=NOW)
    storage.write_live_status(
        store, SESSION.session_id, fixture_stem(SESSION), "finishing", now=NOW,
    )
    terminal_pointer = copy.deepcopy(store.objects["live/current.json"])
    terminal_snapshot = copy.deepcopy(store.objects[pointer["snapshot_key"]])
    with pytest.raises(storage.LiveRecordError, match="snapshot lifecycle"):
        storage.write_live_snapshot(store, pointer, snapshot, now=NOW)
    assert store.objects["live/current.json"] == terminal_pointer
    assert store.objects[pointer["snapshot_key"]] == terminal_snapshot

    store.objects["live/current.json"] = {
        **terminal_pointer,
        "status": "replay_ready",
    }
    with pytest.raises(storage.LiveRecordError, match="snapshot lifecycle"):
        storage.write_live_snapshot(store, pointer, snapshot, now=NOW)


def test_capture_loop_restarts_and_publishes_every_five_seconds_only_with_storage(
    tmp_path, monkeypatch,
):
    import racelens.recorder.worker as worker

    monkeypatch.setattr(worker, "FINISH_GRACE", timedelta(seconds=5))
    monkeypatch.setattr(storage.StorageConfig, "from_env", classmethod(lambda cls: None))

    def run_capture(root, object_store):
        clock = [NOW]
        config = _config(root)
        processes = []
        raw = config.raw_dir / f"{SESSION.session_id}.f1live"
        _write_feed(raw, _feed_prefix())

        class Process:
            def __init__(self, first):
                self.first = first
                self.stopped = False

            def poll(self):
                return 1 if self.first and clock[0] >= NOW + timedelta(seconds=5) else None

            def send_signal(self, _signal):
                self.stopped = True

            def wait(self, timeout=None):
                return 0

            def kill(self):
                self.stopped = True

        def popen(*_args, **_kwargs):
            process = Process(not processes)
            processes.append(process)
            return process

        def sleep(seconds):
            clock[0] += timedelta(seconds=seconds)
            if clock[0] == NOW + timedelta(seconds=5):
                with raw.open("a", encoding="utf-8") as handle:
                    handle.write(_line(
                        "SessionStatus", {"Status": "Finished"},
                        "2026-08-23T13:05:05Z",
                    ) + "\n")

        recorder = Recorder(
            config, now=lambda: clock[0], sleep=sleep, object_store=object_store,
        )
        publishes = []
        monkeypatch.setattr(
            recorder,
            "_publish_live_snapshot",
            lambda *_args: publishes.append(clock[0]) or True,
        )
        monkeypatch.setattr(recorder, "_set_live_status", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(worker.subprocess, "Popen", popen)
        recorder.capture(SESSION)
        return publishes, len(processes)

    publishes, starts = run_capture(tmp_path / "stored", MemoryStore())
    assert publishes == [NOW, NOW + timedelta(seconds=5), NOW + timedelta(seconds=10)]
    assert starts == 2
    publishes, _ = run_capture(tmp_path / "local", None)
    assert publishes == []


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
    store.reads = 0
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


def test_active_remote_sse_closes_without_terminal_end_on_transient_or_stale(
    monkeypatch,
):
    import racelens.api as api

    async def collect_after(initial_store, replacement_store):
        monkeypatch.setattr(api, "_object_store", lambda: initial_store)
        monkeypatch.setattr(api, "_live", None)
        monkeypatch.setattr(api, "_remote_live_cache", None)
        monkeypatch.setattr(api, "_utcnow", lambda: NOW)
        response = await api.live_stream(tick_s=0.5, lang="en", level="pro")
        monkeypatch.setattr(api, "_object_store", lambda: replacement_store)
        api._remote_live_cache = None
        return [chunk async for chunk in response.body_iterator]

    healthy = MemoryStore()
    pointer, snapshot = _valid_records()
    storage.write_live_snapshot(healthy, pointer, snapshot, now=NOW)

    class BrokenStore:
        def get_json(self, *_args, **_kwargs):
            raise StorageError("provider endpoint secret")

    assert asyncio.run(collect_after(healthy, BrokenStore())) == []

    stale = MemoryStore()
    storage.write_live_snapshot(stale, pointer, snapshot, now=NOW)
    stale.objects[pointer["snapshot_key"]]["expires_at"] = (
        NOW - timedelta(seconds=1)
    ).isoformat().replace("+00:00", "Z")
    assert asyncio.run(collect_after(healthy, stale)) == []
