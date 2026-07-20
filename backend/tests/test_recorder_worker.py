import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from racelens.recorder.schedule import ScheduledSession
from racelens.recorder.worker import Config, Recorder, fixture_stem
from racelens.recorder.state import Phase


SESSION = ScheduledSession(
    2026, 13, "Belgian Grand Prix", "R", datetime(2026, 7, 19, 13, tzinfo=UTC)
)


def _config(tmp_path, publish=frozenset({"R"})):
    return Config(
        state_dir=tmp_path / "state", raw_dir=tmp_path / "raw",
        data_dir=tmp_path / "data", interval_seconds=120, capture_poll_seconds=5,
        raw_retention_days=14, publish_sessions=publish,
        transcribe_radio=False, race_core=Path("race-core"),
    )


def test_fixture_stem_is_stable_and_readable():
    assert fixture_stem(SESSION) == "belgian_2026_race"


def test_stage_allows_only_archive_files_and_writes_manifest_last(tmp_path):
    recorder = Recorder(_config(tmp_path))
    archive = tmp_path / "data" / "archive"
    archive.mkdir(parents=True)
    fixture = archive / "belgian_2026_race.jsonl"
    fixture.write_text("fixture", encoding="utf-8")

    recorder._stage(SESSION, [fixture])

    publish = tmp_path / "data" / "publish"
    manifest = json.loads((publish / "belgian_2026_race.ready.json").read_text())
    assert manifest == {"session": "2026-13-r", "files": [fixture.name]}
    with pytest.raises(ValueError, match="outside archive"):
        recorder._stage(SESSION, [tmp_path / "foreign.jsonl"])


def test_config_rejects_unknown_publish_session(tmp_path, monkeypatch):
    monkeypatch.setenv("RACELENS_RECORDER_DATA", str(tmp_path))
    monkeypatch.setenv("RECORDER_PUBLISH_SESSIONS", "R,wat")
    with pytest.raises(ValueError, match="unknown session"):
        Config.from_env()


def test_config_publishes_every_session_type_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("RACELENS_RECORDER_DATA", str(tmp_path))
    monkeypatch.delenv("RECORDER_PUBLISH_SESSIONS", raising=False)
    assert Config.from_env().publish_sessions == frozenset(
        {"FP1", "FP2", "FP3", "Q", "SQ", "Sprint", "R"}
    )


def test_capture_then_processing_retry_never_recaptures(tmp_path, monkeypatch):
    clock = [datetime(2026, 7, 19, 12, 55, tzinfo=UTC)]
    session = ScheduledSession(2026, 13, "Belgian Grand Prix", "R", clock[0])
    recorder = Recorder(_config(tmp_path), now=lambda: clock[0])
    monkeypatch.setattr(
        "racelens.recorder.worker.load_fastf1_schedule", lambda year: [session]
    )
    captures = []
    processes = []
    monkeypatch.setattr(recorder, "capture", lambda item: captures.append(item.session_id))

    def process(item):
        processes.append(item.session_id)
        if len(processes) == 1:
            raise RuntimeError("archive not ready")

    monkeypatch.setattr(recorder, "process", process)

    assert recorder.run_once().startswith("captured:")
    assert recorder.run_once().startswith("processing failed:")
    failed = recorder.store.load().sessions[session.session_id]
    assert failed.phase is Phase.FAILED
    assert failed.retry_phase is Phase.PROCESSING

    clock[0] += timedelta(minutes=16)
    assert recorder.run_once().startswith("complete:")
    assert captures == [session.session_id]
    assert processes == [session.session_id, session.session_id]


def test_restart_resumes_persisted_processing_phase(tmp_path, monkeypatch):
    now = datetime(2026, 7, 19, 15, tzinfo=UTC)
    session = ScheduledSession(2026, 13, "Belgian Grand Prix", "R", now)
    first = Recorder(_config(tmp_path), now=lambda: now)
    first.store.transition(session.session_id, Phase.RECORDING, now)
    first.store.transition(session.session_id, Phase.CAPTURED, now)
    first.store.transition(session.session_id, Phase.PROCESSING, now)

    restarted = Recorder(_config(tmp_path), now=lambda: now)
    monkeypatch.setattr(
        "racelens.recorder.worker.load_fastf1_schedule", lambda year: [session]
    )
    processed = []
    monkeypatch.setattr(restarted, "process", lambda item: processed.append(item.session_id))

    assert restarted.run_once().startswith("complete:")
    assert processed == [session.session_id]


def test_restart_finalizes_recording_after_schedule_deadline(tmp_path, monkeypatch):
    start = datetime(2026, 7, 19, 10, tzinfo=UTC)
    now = start + timedelta(hours=5)
    session = ScheduledSession(2026, 13, "Belgian Grand Prix", "R", start)
    recorder = Recorder(_config(tmp_path), now=lambda: now)
    recorder.store.transition(session.session_id, Phase.RECORDING, start)
    monkeypatch.setattr(
        "racelens.recorder.worker.load_fastf1_schedule", lambda year: [session]
    )
    captures = []
    monkeypatch.setattr(recorder, "capture", lambda item: captures.append(item.session_id))

    assert recorder.run_once().startswith("captured:")
    assert captures == [session.session_id]
