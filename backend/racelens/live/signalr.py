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

The fetch re-parses the whole file every poll. Incremental parsing is only
worth adding if this becomes measurable at the end of a race.
"""
from __future__ import annotations

import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Callable

from racelens.events.models import Event
from racelens.recorder.schedule import canonical_alias

_FINISHED = {"Ends", "Finished", "Finalised"}


def _name(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in normalized if char.isalnum() or char.isspace())
        .lower()
        .split()
    )


def _matches_target(
    info: dict, year: int, gp: str, session: str,
) -> bool:
    meeting = info.get("Meeting")
    if not isinstance(meeting, dict):
        return False
    requested = _name(gp)
    circuit = meeting.get("Circuit")
    country = meeting.get("Country")
    candidates = [
        meeting.get("Name"),
        meeting.get("OfficialName"),
        meeting.get("Location"),
        circuit.get("ShortName") if isinstance(circuit, dict) else None,
        country.get("Name") if isinstance(country, dict) else None,
    ]
    return (
        str(info.get("StartDate") or "").startswith(str(year))
        and canonical_alias(info.get("Name")) == canonical_alias(session)
        and any(
            requested == candidate
            or len(requested) >= 3 and requested in candidate
            or len(candidate) >= 3 and candidate in requested
            for value in candidates
            if (candidate := _name(value))
        )
    )


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
            "-o", str(self.out_path), "--timeout", "0", "--append",
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
    from racelens.adapters.f1live_adapter import (
        current_f1live_session_info,
        ingest_f1live,
    )

    session_id = f"{gp}_{year}_{session}".lower().replace(" ", "_")

    signature: tuple[int, int] | None = None
    cached: list[Event] = []

    def fetch() -> list[Event]:
        nonlocal signature, cached
        if not feed_path.is_file() or feed_path.stat().st_size == 0:
            return []
        stat = feed_path.stat()
        current = (stat.st_size, stat.st_mtime_ns)
        if current != signature:
            info = current_f1live_session_info(str(feed_path))
            target_ready = info is not None and _matches_target(info, year, gp, session)
            finished_before_join = (
                not cached
                and info is not None
                and info.get("SessionStatus") in _FINISHED
            )
            cached = (
                ingest_f1live(str(feed_path), session_id=session_id)
                if target_ready and not finished_before_join
                else []
            )
            signature = current
        return cached

    return fetch
