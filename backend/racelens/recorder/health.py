"""Container health check for the unattended recorder."""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from racelens.recorder.state import Phase, StateStore
from racelens.recorder.worker import PROCESS_TIMEOUT

MAX_IDLE_AGE = 5 * 60
MAX_PROCESSING_AGE = PROCESS_TIMEOUT + 5 * 60


def _require_fresh(path: Path, now: datetime, max_age: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing regular file: {path.name}")
    age = now.timestamp() - path.stat().st_mtime
    if age < -60 or age > max_age:
        raise RuntimeError(f"stale file: {path.name} ({age:.0f}s)")


def check(base: Path, now: datetime | None = None) -> None:
    current = now or datetime.now(UTC)
    if (base / "state" / "schedule-failure").is_file():
        raise RuntimeError("schedule unavailable")
    state = StateStore(base / "state" / "recorder.json").load()
    processing = (
        any(item.phase is Phase.PROCESSING for item in state.sessions.values())
        or (base / "state" / "remote-processing").is_file()
    )
    _require_fresh(
        base / "state" / "heartbeat",
        current,
        MAX_PROCESSING_AGE if processing else MAX_IDLE_AGE,
    )
    for session_id, item in state.sessions.items():
        if item.phase is Phase.RECORDING:
            _require_fresh(base / "raw" / f"{session_id}.f1live", current, MAX_IDLE_AGE)


def main() -> None:
    base = Path(os.environ.get("RACELENS_RECORDER_DATA", "/var/lib/race-lens-recorder"))
    try:
        check(base)
    except Exception as exc:
        print(f"recorder unhealthy: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
