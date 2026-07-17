import os
from datetime import UTC, datetime, timedelta

import pytest

from racelens.recorder.health import check
from racelens.recorder.state import Phase, StateStore


def test_health_rejects_a_stalled_recording(tmp_path):
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    state_dir = tmp_path / "state"
    raw_dir = tmp_path / "raw"
    state_dir.mkdir()
    raw_dir.mkdir()
    heartbeat = state_dir / "heartbeat"
    heartbeat.touch()
    raw = raw_dir / "2026-10-fp1.f1live"
    raw.touch()
    StateStore(state_dir / "recorder.json").transition("2026-10-fp1", Phase.RECORDING, now)
    fresh = now.timestamp()
    os.utime(heartbeat, (fresh, fresh))
    os.utime(raw, (fresh, fresh))

    check(tmp_path, now)
    stale = (now - timedelta(minutes=6)).timestamp()
    os.utime(raw, (stale, stale))

    with pytest.raises(RuntimeError, match="stale file"):
        check(tmp_path, now)
