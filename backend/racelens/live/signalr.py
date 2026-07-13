"""SignalR live source: capture subprocess + fetch closure for LiveRunner.

The free F1 live-timing SignalR feed replaces the paid OpenF1 realtime tier:

    SignalRClient (subprocess, writes feed file)
        → make_signalr_fetch(file) re-parses the growing file each poll
        → LiveRunner rebuilds the engine (its normal contract)
        → same RaceFrame / /api/live endpoints, frontend unchanged.

The capture runs as a SUBPROCESS (`python -m racelens.cli capture-live`):
SignalRClient.start() blocks and owns its own connection loop, so in-process
it would fight uvicorn's event loop, and a feed crash must not kill the API.
The feed file also doubles as the post-race recording — even if live mode
fails, `racelens ingest-live` turns it into a replay fixture afterwards.

ponytail: fetch re-parses the WHOLE file every poll — O(n) per poll, ~seconds
by race end at poll_s>=5. Incremental parsing only if that measurably hurts.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from racelens.events.models import Event


class SignalRCapture:
    """Supervises the capture-live CLI as a child process."""

    def __init__(self, out_path: Path, no_auth: bool = False) -> None:
        self.out_path = out_path
        self._no_auth = no_auth
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "-m", "racelens.cli", "capture-live",
            "-o", str(self.out_path), "--timeout", "0",
        ]
        if self._no_auth:
            cmd.append("--no-auth")
        # stderr → our stderr so capture problems show in the API log.
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL)

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


def make_signalr_fetch(
    feed_path: Path, year: int, gp: str, session: str,
) -> Callable[[], list[Event]]:
    """Build the LiveRunner fetch: full-snapshot re-parse of the feed file.

    Returns [] while the file is missing/empty (capture connecting) so the
    runner reports a clean "no data yet" instead of counting failures.
    """
    # Direct feed parser — fastf1's livedata path cannot build laps from a
    # live/mid-join recording (drops keyframes, archive-grade lap builder), so
    # live uses our own TimingData mapping. fastf1 stays for post-race replays.
    from racelens.adapters.f1live_adapter import ingest_f1live

    session_id = f"{gp}_{year}_{session}".lower().replace(" ", "_")

    def fetch() -> list[Event]:
        if not feed_path.is_file() or feed_path.stat().st_size == 0:
            return []
        return ingest_f1live(str(feed_path), session_id=session_id)

    return fetch
