import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import racelens.recorder.state as state_module
from racelens.recorder.state import (
    CorruptStateError,
    Phase,
    RecorderState,
    StateStore,
)


NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
SID = "2026-12-r"


def test_missing_state_is_empty(tmp_path):
    state = StateStore(tmp_path / "recorder.json").load()
    assert state == RecorderState()
    assert state.can_attempt(SID, NOW)
    assert state.due_phase(SID, NOW) is Phase.RECORDING
    with pytest.raises(ValueError, match="timezone-aware"):
        state.can_attempt(SID, datetime(2026, 7, 17, 12))


def test_atomic_roundtrip_and_idempotent_recording_transition(tmp_path, monkeypatch):
    path = tmp_path / "state" / "recorder.json"
    store = StateStore(path)
    real_replace = os.replace
    replacements = []

    def replace(source, target):
        replacements.append((source, target, Path(source).parent))
        real_replace(source, target)

    monkeypatch.setattr(state_module.os, "replace", replace)

    first = store.transition(SID, Phase.RECORDING, NOW)
    original = path.read_bytes()
    second = store.transition(SID, Phase.RECORDING, NOW + timedelta(minutes=1))

    assert first == second == store.load()
    assert first.sessions[SID].attempts == 1
    assert path.read_bytes() == original
    assert len(replacements) == 1
    assert replacements[0][1] == path
    assert replacements[0][2] == path.parent
    assert not list(path.parent.glob("*.tmp"))


def test_complete_phase_sequence_and_no_regression(tmp_path):
    store = StateStore(tmp_path / "recorder.json")
    store.transition(SID, Phase.RECORDING, NOW)
    store.transition(SID, Phase.CAPTURED, NOW + timedelta(hours=1))
    store.transition(SID, Phase.PROCESSING, NOW + timedelta(hours=2))
    final = store.transition(SID, Phase.COMPLETE, NOW + timedelta(hours=3))

    assert final.sessions[SID].phase is Phase.COMPLETE
    with pytest.raises(ValueError, match="invalid transition"):
        store.transition(SID, Phase.RECORDING, NOW + timedelta(hours=4))


def test_retry_metadata_and_attempt_count(tmp_path):
    store = StateStore(tmp_path / "recorder.json")
    store.transition(SID, Phase.RECORDING, NOW)
    retry_at = NOW + timedelta(minutes=15)
    failed = store.transition(
        SID, Phase.FAILED, NOW + timedelta(minutes=1), error="feed down", retry_at=retry_at
    )

    assert failed.sessions[SID].last_error == "feed down"
    assert not failed.can_attempt(SID, retry_at - timedelta(microseconds=1))
    assert failed.can_attempt(SID, retry_at)

    retried = store.transition(SID, Phase.RECORDING, retry_at)
    item = retried.sessions[SID]
    assert item.attempts == 2
    assert item.last_error is None
    assert item.retry_at is None
    assert item.retry_phase is None


def test_processing_retry_does_not_repeat_capture(tmp_path):
    store = StateStore(tmp_path / "recorder.json")
    store.transition(SID, Phase.RECORDING, NOW)
    store.transition(SID, Phase.CAPTURED, NOW + timedelta(hours=1))
    store.transition(SID, Phase.PROCESSING, NOW + timedelta(hours=2))
    retry_at = NOW + timedelta(hours=3)
    failed = store.transition(
        SID, Phase.FAILED, NOW + timedelta(hours=2, minutes=1),
        error="transcode failed", retry_at=retry_at,
    )

    assert failed.sessions[SID].retry_phase is Phase.PROCESSING
    assert failed.sessions[SID].attempts == 1
    assert failed.due_phase(SID, retry_at) is Phase.PROCESSING
    with pytest.raises(ValueError, match="retry is not due"):
        store.transition(SID, Phase.PROCESSING, retry_at - timedelta(seconds=1))
    with pytest.raises(ValueError, match="invalid transition"):
        store.transition(SID, Phase.RECORDING, retry_at)

    retrying = store.transition(SID, Phase.PROCESSING, retry_at)
    assert retrying.sessions[SID].attempts == 1


def test_failed_phase_requires_complete_retry_metadata(tmp_path):
    store = StateStore(tmp_path / "recorder.json")
    store.transition(SID, Phase.RECORDING, NOW)
    with pytest.raises(ValueError, match="requires error"):
        store.transition(SID, Phase.FAILED, NOW, error="broken")


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        json.dumps({"version": 2, "sessions": {}}),
        json.dumps({"version": 1, "sessions": {SID: {"phase": "wat"}}}),
        json.dumps({"version": 1, "sessions": {"bad-id": {}}}),
        json.dumps({
            "version": 1,
            "sessions": {SID: {
                "phase": "recording", "attempts": 1,
                "updated_at": "2026-07-17T12:00:00",
            }},
        }),
    ],
)
def test_corrupt_state_fails_closed_and_is_never_overwritten(tmp_path, payload):
    path = tmp_path / "recorder.json"
    path.write_text(payload, encoding="utf-8")
    store = StateStore(path)

    with pytest.raises(CorruptStateError):
        store.load()
    with pytest.raises(CorruptStateError):
        store.save(RecorderState())
    with pytest.raises(CorruptStateError):
        store.transition(SID, Phase.RECORDING, NOW)
    assert path.read_text(encoding="utf-8") == payload


def test_atomic_replace_failure_leaves_no_partial_state(tmp_path, monkeypatch):
    path = tmp_path / "recorder.json"
    store = StateStore(path)

    def fail_replace(source, target):
        raise OSError("disk unavailable")

    monkeypatch.setattr(state_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk unavailable"):
        store.transition(SID, Phase.RECORDING, NOW)

    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))
