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


def _repair_feed(feed_path: Path) -> Path:
    """Mid-join repair: make the subscribe KEYFRAMES readable by fastf1.

    fastf1 3.8.3's LiveTimingData drops every keyframe line the feed sends on
    subscribe: their payload is a JSON *string* (breaks `_fix_json`'s naive
    quote swap) and their timestamp is empty (parsed lines need one). Joining
    mid-session, the keyframes ARE the session history — dropping them leaves
    fastf1 with no SessionInfo/DriverList/session start, so nothing parses.

    Repair (into a patched copy):
      * decode every keyframe payload to a python dict (the live-message
        on-disk form, which `_fix_json` handles) and stamp it with the
        session-start UTC taken from the SessionData keyframe's StatusSeries;
      * put the repaired SessionData keyframe FIRST — fastf1's start-date
        skimmer takes the first 'SessionStatus'+'Started' line and requires
        it to carry StatusSeries (KeyError otherwise, uncaught);
      * inject a timestamped SessionStatus 'Started' line (anchors
        session_start_time for lap parsing);
      * keep incremental (timestamped) lines untouched, in order.

    No-op if a timestamped Started line is already present (joined pre-start).
    """
    import ast
    import json

    lines = feed_path.read_text(encoding="utf-8-sig").splitlines()

    started_utc = None
    session_data_line = None
    keyframes: list[str] = []
    incremental: list[str] = []

    for ln in lines:
        if not ln.startswith("["):
            continue
        try:
            row = ast.literal_eval(ln)
        except (ValueError, SyntaxError):
            incremental.append(ln)  # not our business — let fastf1 decide
            continue
        if len(row) < 3:
            continue
        cat, payload, ts = row[0], row[1], row[2]

        if ts:  # live incremental line — keep verbatim
            # NB: a timestamped 'Started' here can be a mid-session SEGMENT
            # start (quali Q2/Q3) — it does NOT mean we joined pre-start, so
            # keyframes still need repairing. No early exit.
            incremental.append(ln)
            continue

        # Keyframe: decode string payload to dict.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if cat == "SessionData":
            for item in (payload.get("StatusSeries") or []):
                if isinstance(item, dict) and item.get("SessionStatus") == "Started":
                    started_utc = item.get("Utc")
            session_data_line = (cat, payload)
        else:
            keyframes.append((cat, payload))

    if started_utc is None:
        return feed_path  # nothing to anchor with — let the parser cope

    patched = feed_path.with_name(feed_path.stem + ".patched.txt")
    out: list[str] = []
    # SessionData first: the start-date skimmer needs it before any other
    # 'SessionStatus'-mentioning line.
    if session_data_line is not None:
        out.append(str([session_data_line[0], session_data_line[1], started_utc]))
    out.append(str(["SessionStatus", {"Status": "Started", "Started": "Started"}, started_utc]))
    for cat, payload in keyframes:
        out.append(str([cat, payload, started_utc]))
    out.extend(incremental)
    patched.write_text("\n".join(out) + "\n", encoding="utf-8")
    return patched


# Back-compat alias (previous name).
_ensure_session_start = _repair_feed


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
