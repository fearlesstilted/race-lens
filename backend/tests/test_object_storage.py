import copy
import hashlib
from pathlib import Path

import pytest

from racelens.object_storage import (
    MAX_OBJECT_BYTES,
    ManifestError,
    ObjectPreparationQueue,
    RemoteSessionCache,
    load_manifest,
    publish_session,
    validate_manifest,
)
from racelens.preparations import QueueFullError


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.operations = []

    def list_keys(self, prefix, *, limit=1000):
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        if len(keys) > limit:
            raise RuntimeError("too many")
        return keys

    def get_json(self, key, *, limit):
        value = self.objects.get(key)
        return copy.deepcopy(value) if isinstance(value, dict) else None

    def put_json(self, key, value):
        self.operations.append(("put_json", key))
        self.objects[key] = copy.deepcopy(value)

    def upload_file(self, key, path, *, sha256):
        data = Path(path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha256
        self.operations.append(("upload", key))
        self.objects[key] = data

    def verify(self, key, *, size, sha256):
        data = self.objects[key]
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
            raise ManifestError("checksum")

    def matches(self, key, *, size, sha256):
        data = self.objects.get(key)
        return (
            isinstance(data, bytes)
            and len(data) == size
            and hashlib.sha256(data).hexdigest() == sha256
        )

    def copy(self, source, destination):
        self.operations.append(("copy", destination))
        self.objects[destination] = self.objects[source]

    def delete(self, key):
        self.objects.pop(key, None)

    def download_verified(self, key, destination, *, size, sha256):
        data = self.objects[key]
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
            raise ManifestError("checksum")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def _archive(tmp_path):
    paths = []
    for name, content in (
        ("race.jsonl", b'{"event":"lap"}\n'),
        ("race.track.json", b'{"points":[[0,0],[1,1]]}\n'),
        ("race.positions.json", b'{"drivers":{"VER":[[0,0]]}}\n'),
    ):
        path = tmp_path / name
        path.write_bytes(content)
        paths.append(path)
    return paths


def test_manifest_is_final_and_remote_cache_rejects_corruption(tmp_path):
    store = MemoryStore()
    fixture, track, positions = _archive(tmp_path)
    manifest = publish_session(
        store,
        "2024-08-r",
        "monaco_2024_race",
        fixture,
        track,
        positions,
        event_count=1,
    )

    assert store.operations[-1] == (
        "put_json",
        "sessions/monaco_2024_race/manifest.json",
    )
    assert load_manifest(store, "monaco_2024_race") == manifest
    cache = RemoteSessionCache(store, tmp_path / "cache")
    root = cache.materialize("monaco_2024_race")
    assert (root / "monaco_2024_race.jsonl").read_bytes() == fixture.read_bytes()

    store.objects["sessions/monaco_2024_race/events.jsonl"] = b"corrupt"
    (root / ".manifest-sha256").unlink()
    with pytest.raises(ManifestError, match="checksum"):
        cache.materialize("monaco_2024_race")


def test_manifest_rejects_oversized_or_unexpected_objects(tmp_path):
    store = MemoryStore()
    fixture, track, positions = _archive(tmp_path)
    manifest = publish_session(
        store,
        "2024-08-r",
        "monaco_2024_race",
        fixture,
        track,
        positions,
        event_count=1,
    )
    manifest["files"]["events.jsonl"]["size"] = MAX_OBJECT_BYTES + 1
    with pytest.raises(ManifestError, match="events.jsonl"):
        validate_manifest(manifest)

    manifest = store.objects["sessions/monaco_2024_race/manifest.json"]
    manifest["files"]["extra"] = {
        "key": "sessions/monaco_2024_race/extra",
        "size": 1,
        "sha256": "0" * 64,
    }
    with pytest.raises(ManifestError, match="file set"):
        validate_manifest(manifest)


def test_object_queue_is_bounded_idempotent_and_retries_after_worker_failure():
    store = MemoryStore()
    queue = ObjectPreparationQueue(store, max_jobs=1, daily_max=1, max_attempts=2)

    first, created = queue.enqueue("2024-08-r", "monaco_2024_race")
    duplicate, created_again = queue.enqueue("2024-08-r", "monaco_2024_race")
    assert created is True
    assert created_again is False
    assert duplicate == first
    with pytest.raises(QueueFullError):
        queue.enqueue("2024-09-r", "canada_2024_race")

    claimed = queue.claim_next()
    assert claimed["status"] == "processing"
    retry = queue.finish("2024-08-r", error="secret-key-must-not-leak")
    assert retry["status"] == "queued"
    assert "secret-key" not in retry["error"]
    retry["retry_at"] = None
    store.put_json("status/2024-08-r.json", retry)
    claimed_again = queue.claim_next()
    assert claimed_again["attempts"] == 2
    failed = queue.finish("2024-08-r", error="Archive source is unavailable")
    assert failed["status"] == "failed"

    retried, retried_now = queue.enqueue("2024-08-r", "monaco_2024_race")
    assert retried_now is True
    assert retried["status"] == "queued"
    assert retried["generation"] == 2


def test_ready_queue_record_disappears_when_an_archive_object_is_corrupt(tmp_path):
    store = MemoryStore()
    fixture, track, positions = _archive(tmp_path)
    queue = ObjectPreparationQueue(store)
    queue.enqueue("2024-08-r", "monaco_2024_race")
    queue.claim_next()
    publish_session(
        store,
        "2024-08-r",
        "monaco_2024_race",
        fixture,
        track,
        positions,
        event_count=1,
    )
    queue.finish("2024-08-r", replay_session_id="monaco_2024_race")
    store.objects["sessions/monaco_2024_race/events.jsonl"] = b"corrupt"
    queue._cache = None

    record = queue.get("2024-08-r")
    assert record["status"] == "failed"
    assert record["replay_session_id"] is None
