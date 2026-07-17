import importlib.util
import json
from pathlib import Path

import pytest


_PATH = Path(__file__).resolve().parents[2] / "deploy" / "recorder" / "publish.py"
_SPEC = importlib.util.spec_from_file_location("recorder_publisher", _PATH)
assert _SPEC and _SPEC.loader
publisher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(publisher)


def _staged(tmp_path):
    stem = "belgian_2026_race"
    staging = tmp_path / "publish"
    staging.mkdir(parents=True)
    names = [f"{stem}.jsonl", f"{stem}.track.json", f"{stem}.positions.json"]
    for name in names:
        (staging / name).write_text("{}\n", encoding="utf-8")
    manifest = staging / f"{stem}.ready.json"
    manifest.write_text(
        json.dumps({"session": "2026-10-r", "files": names}), encoding="utf-8"
    )
    return staging, manifest


def test_manifest_accepts_exact_fixture_triplet(tmp_path):
    staging, manifest = _staged(tmp_path)
    descriptor = publisher.os.open(staging, publisher.os.O_RDONLY | publisher.os.O_DIRECTORY)
    try:
        stem, sources = publisher.manifest_files(manifest.name, descriptor)
        assert stem == "belgian_2026_race"
        assert set(sources) == {
            "belgian_2026_race.jsonl",
            "belgian_2026_race.track.json",
            "belgian_2026_race.positions.json",
        }
    finally:
        publisher.os.close(descriptor)


def test_manifest_rejects_extra_file_and_symlink(tmp_path):
    staging, manifest = _staged(tmp_path)
    data = json.loads(manifest.read_text())
    data["files"].append("README.md")
    manifest.write_text(json.dumps(data), encoding="utf-8")
    descriptor = publisher.os.open(staging, publisher.os.O_RDONLY | publisher.os.O_DIRECTORY)
    try:
        with pytest.raises(ValueError, match="file set"):
            publisher.manifest_files(manifest.name, descriptor)
    finally:
        publisher.os.close(descriptor)

    staging, manifest = _staged(tmp_path / "second")
    position = staging / "belgian_2026_race.positions.json"
    position.unlink()
    position.symlink_to(staging / "belgian_2026_race.track.json")
    descriptor = publisher.os.open(staging, publisher.os.O_RDONLY | publisher.os.O_DIRECTORY)
    try:
        with pytest.raises(OSError):
            publisher.manifest_files(manifest.name, descriptor)
    finally:
        publisher.os.close(descriptor)
