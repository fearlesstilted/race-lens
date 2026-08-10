import json
import os
import sys
from datetime import UTC, datetime, timedelta

from racelens.recorder.state import Phase, StateStore
from racelens.recorder.status import recorder_status


def test_recorder_status_reports_current_files_without_paths_or_errors(
    tmp_path, monkeypatch, capsys,
):
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    state_dir = tmp_path / "state"
    raw_dir = tmp_path / "raw"
    publish_dir = tmp_path / "data" / "publish"
    state_dir.mkdir()
    raw_dir.mkdir()
    publish_dir.mkdir(parents=True)
    heartbeat = state_dir / "heartbeat"
    raw = raw_dir / "2026-10-fp1.f1live"
    heartbeat.write_text("", encoding="utf-8")
    raw.write_bytes(b"secret transport")
    timestamp = (now - timedelta(seconds=5)).timestamp()
    os.utime(heartbeat, (timestamp, timestamp))
    os.utime(raw, (timestamp, timestamp))
    StateStore(state_dir / "recorder.json").transition(
        "2026-10-fp1", Phase.RECORDING, now - timedelta(seconds=10),
    )
    (publish_dir / "belgian_2026_fp1.ready.json").write_text(
        json.dumps({"session": "2026-10-fp1", "files": []}), encoding="utf-8",
    )

    body = recorder_status(tmp_path, now)

    assert body == {
        "heartbeat_age_seconds": 5.0,
        "session": {
            "session_id": "2026-10-fp1",
            "phase": "recording",
            "updated_age_seconds": 10.0,
        },
        "raw": {"size_bytes": 16, "age_seconds": 5.0},
        "publication": "pending",
    }
    encoded = json.dumps(body)
    assert str(tmp_path) not in encoded
    assert "secret transport" not in encoded

    from racelens import cli

    monkeypatch.setenv("RACELENS_RECORDER_DATA", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["racelens", "recorder-status", "--json"])
    cli.main()
    command = json.loads(capsys.readouterr().out)
    assert command["session"]["session_id"] == "2026-10-fp1"
    assert str(tmp_path) not in json.dumps(command)


def test_recorder_status_cli_sanitizes_corrupt_state(tmp_path, monkeypatch, capsys):
    from racelens import cli

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "recorder.json").write_text("not json: /private/recorder", encoding="utf-8")
    monkeypatch.setenv("RACELENS_RECORDER_DATA", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["racelens", "recorder-status", "--json"])

    cli.main()
    output = capsys.readouterr()
    body = json.loads(output.out)

    assert output.err == ""
    assert body["error"] == "state_unavailable"
    assert str(tmp_path) not in output.out
    assert "/private/recorder" not in output.out


def test_recorder_status_sanitizes_state_permission_failure(tmp_path, monkeypatch):
    def denied(_self):
        raise PermissionError(f"denied: {tmp_path}")

    monkeypatch.setattr(StateStore, "load", denied)

    body = recorder_status(tmp_path)

    assert body["error"] == "state_unavailable"
    assert str(tmp_path) not in json.dumps(body)
