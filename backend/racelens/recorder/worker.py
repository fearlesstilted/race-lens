"""Unattended recorder: schedule -> SignalR -> archive -> publish staging."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from racelens.object_storage import (
    ObjectPreparationQueue,
    S3Store,
    StorageConfig,
    publish_session,
)
from racelens.recorder.feed import inspect_feed, isolate_session
from racelens.recorder.postprocess import merge_captured_radio, validate_archive, validate_fixture
from racelens.recorder.schedule import ScheduledSession, load_fastf1_schedule, select_due_session
from racelens.recorder.state import Phase, StateStore

FINISH_GRACE = timedelta(minutes=10)
CAPTURE_RETRY = timedelta(minutes=5)
ARCHIVE_RETRY = timedelta(minutes=15)
PROCESS_TIMEOUT = 60 * 60
SCHEDULE_REFRESH = timedelta(hours=6)
REMOTE_CAPTURE_GUARD = timedelta(hours=2)
SESSION_LABEL = {"R": "race", "Q": "qualifying", "SQ": "sprint_qualifying"}


def _positive_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def fixture_stem(session: ScheduledSession) -> str:
    venue = re.sub(r"\s+grand prix$", "", session.event_name, flags=re.IGNORECASE)
    label = SESSION_LABEL.get(session.kind, session.kind.lower())
    return f"{_slug(venue)}_{session.year}_{label}"


@dataclass(frozen=True, slots=True)
class Config:
    state_dir: Path
    raw_dir: Path
    data_dir: Path
    interval_seconds: int
    capture_poll_seconds: int
    raw_retention_days: int
    publish_sessions: frozenset[str]
    transcribe_radio: bool
    race_core: Path
    git_publication: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        base = Path(os.environ.get("RACELENS_RECORDER_DATA", "/var/lib/race-lens-recorder"))
        publish = {
            item.strip()
            for item in os.environ.get(
                "RECORDER_PUBLISH_SESSIONS", "FP1,FP2,FP3,Q,SQ,Sprint,R"
            ).split(",")
            if item.strip()
        }
        valid = {"FP1", "FP2", "FP3", "SQ", "Sprint", "Q", "R"}
        if not publish <= valid:
            raise ValueError("RECORDER_PUBLISH_SESSIONS contains an unknown session")
        transcribe = os.environ.get("RECORDER_TRANSCRIBE_RADIO", "1").lower() in {
            "1", "true", "yes",
        }
        git_publication = os.environ.get("RECORDER_GIT_PUBLICATION", "1").lower() in {
            "1", "true", "yes",
        }
        return cls(
            state_dir=base / "state",
            raw_dir=base / "raw",
            data_dir=base / "data",
            interval_seconds=_positive_int("RECORDER_INTERVAL_SEC", 120, 30),
            capture_poll_seconds=_positive_int("RECORDER_CAPTURE_POLL_SEC", 5),
            raw_retention_days=_positive_int("RECORDER_RAW_RETENTION_DAYS", 14),
            publish_sessions=frozenset(publish),
            transcribe_radio=transcribe,
            race_core=Path(os.environ.get("RACELENS_RACE_CORE", "/usr/local/bin/race-core")),
            git_publication=git_publication,
        )


class Recorder:
    def __init__(
        self,
        config: Config,
        *,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        object_store: object | None = None,
    ) -> None:
        self.config = config
        self.now = now or (lambda: datetime.now(UTC))
        self.sleep = sleep
        self.store = StateStore(config.state_dir / "recorder.json")
        self.heartbeat = config.state_dir / "heartbeat"
        self.remote_processing = config.state_dir / "remote-processing"
        self._schedule: list[ScheduledSession] = []
        self._schedule_loaded_at: datetime | None = None
        self._schedule_years: set[int] = set()
        if object_store is None:
            storage_config = StorageConfig.from_env()
            object_store = S3Store(storage_config) if storage_config is not None else None
        self.object_store = object_store
        self.remote_queue = (
            ObjectPreparationQueue(object_store) if object_store is not None else None
        )
        for path in (config.state_dir, config.raw_dir, config.data_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.remote_processing.unlink(missing_ok=True)

    def _beat(self) -> None:
        self.heartbeat.touch()

    def _paths(self, session: ScheduledSession) -> dict[str, Path]:
        stem = fixture_stem(session)
        archive = self.config.data_dir / "archive"
        return {
            "raw": self.config.raw_dir / f"{session.session_id}.f1live",
            "clean": self.config.raw_dir / f"{session.session_id}.clean.f1live",
            "provisional": archive / f"{stem}.provisional.jsonl",
            "fixture": archive / f"{stem}.jsonl",
            "track": archive / f"{stem}.track.json",
            "positions_raw": self.config.raw_dir / f"{session.session_id}.positions.jsonl",
            "positions": archive / f"{stem}.positions.json",
            "publish": self.config.data_dir / "publish",
        }

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    def capture(self, session: ScheduledSession) -> Path:
        paths = self._paths(session)
        raw, clean = paths["raw"], paths["clean"]
        prior = inspect_feed(raw, session)
        if prior.matched and (prior.finished or self.now() >= session.capture_until):
            isolate_session(raw, clean, session)
            return clean

        command = [
            sys.executable, "-m", "racelens.cli", "capture-live",
            "--no-auth", "--timeout", "0", "--append", "-o", str(raw),
        ]
        process = subprocess.Popen(command, start_new_session=True)
        finished_at: datetime | None = None
        try:
            while True:
                self._beat()
                now = self.now()
                inspection = inspect_feed(raw, session)
                if inspection.finished and finished_at is None:
                    finished_at = now
                if finished_at is not None and now >= finished_at + FINISH_GRACE:
                    break
                if now >= session.capture_until:
                    break
                status = process.poll()
                if status is not None:
                    if finished_at is None:
                        raise RuntimeError(f"capture exited before session finish ({status})")
                    self.sleep(self.config.capture_poll_seconds)
                    process = subprocess.Popen(command, start_new_session=True)
                    continue
                self.sleep(self.config.capture_poll_seconds)
        finally:
            self._stop(process)

        inspection = inspect_feed(raw, session)
        if not inspection.matched:
            raise RuntimeError("live feed never matched the scheduled session")
        isolate_session(raw, clean, session)
        return clean

    def _run(self, argv: list[str], *, env: dict[str, str] | None = None) -> None:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        self._beat()
        process = subprocess.Popen(argv, env=merged_env)
        deadline = time.monotonic() + PROCESS_TIMEOUT
        try:
            while process.poll() is None:
                self._beat()
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(argv, PROCESS_TIMEOUT)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, argv)
        finally:
            self._stop(process)
            self._beat()

    def _stage(self, session: ScheduledSession, artifacts: list[Path]) -> None:
        destination = self._paths(session)["publish"]
        destination.mkdir(parents=True, exist_ok=True)
        names = []
        for source in artifacts:
            if source.parent != self.config.data_dir / "archive":
                raise ValueError("refusing to stage an artifact outside archive")
            target = destination / source.name
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
            names.append(source.name)
        manifest = destination / f"{fixture_stem(session)}.ready.json"
        temporary = manifest.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"session": session.session_id, "files": sorted(names)}) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, manifest)

    def _build_archive(
        self,
        session: ScheduledSession,
        *,
        captured: Path | None,
        full: bool,
    ) -> tuple[list[Path], int]:
        paths = self._paths(session)
        archive_dir = paths["fixture"].parent
        archive_dir.mkdir(parents=True, exist_ok=True)
        env = {
            "RACELENS_FIXTURES": str(archive_dir),
            "FASTF1_CACHE": str(self.config.data_dir / "fastf1_cache"),
        }
        self._run([
            sys.executable, "-m", "racelens.cli", "ingest", str(session.year),
            session.event_name, session.kind, "-o", str(paths["fixture"]),
        ], env=env)
        if captured is not None:
            merge_captured_radio(paths["fixture"], captured)
        if captured is not None and self.config.transcribe_radio:
            self._run([
                sys.executable, "-m", "racelens.cli", "radio-transcribe",
                str(paths["fixture"]),
            ], env=env)
        event_count = validate_fixture(paths["fixture"])
        if not full:
            return [paths["fixture"]], event_count
        self._run([
            sys.executable, "-m", "racelens.cli", "track", str(session.year),
            session.event_name, session.kind, "-o", str(paths["track"]),
        ], env=env)
        self._run([
            sys.executable, "-m", "racelens.cli", "positions-raw", str(session.year),
            session.event_name, session.kind, "-o", str(paths["positions_raw"]),
        ], env=env)
        self._run([
            str(self.config.race_core), str(paths["positions_raw"]),
            str(paths["track"]), str(paths["positions"]), "1000",
        ], env=env)
        self._run([
            sys.executable, "-m", "racelens.cli", "track-progress", str(session.year),
            session.event_name, session.kind, fixture_stem(session),
        ], env=env)
        report = validate_archive(paths["fixture"], paths["track"], paths["positions"])
        paths["positions_raw"].unlink(missing_ok=True)
        return [paths["fixture"], paths["track"], paths["positions"]], report.events

    def _publish(
        self,
        session: ScheduledSession,
        artifacts: list[Path],
        event_count: int,
    ) -> None:
        if self.config.git_publication:
            self._stage(session, artifacts)
        if self.object_store is not None:
            replay_id = fixture_stem(session)
            publish_session(
                self.object_store,
                session.session_id,
                replay_id,
                *artifacts,
                event_count=event_count,
            )
            self.remote_queue.finish(
                session.session_id,
                replay_session_id=replay_id,
            )

    def process(self, session: ScheduledSession) -> None:
        paths = self._paths(session)
        clean = paths["clean"]
        if not clean.is_file():
            isolate_session(paths["raw"], clean, session)
        archive_dir = paths["fixture"].parent
        archive_dir.mkdir(parents=True, exist_ok=True)
        env = {
            "RACELENS_FIXTURES": str(archive_dir),
            "FASTF1_CACHE": str(self.config.data_dir / "fastf1_cache"),
        }
        self._run([
            sys.executable, "-m", "racelens.cli", "ingest-live", str(clean),
            "--year", str(session.year), "--gp", session.event_name,
            "--session", session.kind, "-o", str(paths["provisional"]),
        ], env=env)
        full = session.kind in self.config.publish_sessions
        artifacts, event_count = self._build_archive(
            session, captured=paths["provisional"], full=full,
        )
        if full:
            self._publish(session, artifacts, event_count)

    def process_requested(self, session: ScheduledSession, replay_id: str) -> None:
        if fixture_stem(session) != replay_id:
            raise RuntimeError("requested replay ID differs from the FastF1 schedule")
        artifacts, event_count = self._build_archive(session, captured=None, full=True)
        self._publish(session, artifacts, event_count)

    def _run_remote_once(self) -> str:
        if self.remote_queue is None:
            return "idle"
        job = self.remote_queue.claim_next(self.now())
        if job is None:
            return "idle"
        session_id = job["session_id"]
        self.remote_processing.touch()
        try:
            year = int(session_id.split("-", 1)[0])
            matches = [
                session
                for session in load_fastf1_schedule(year)
                if session.session_id == session_id
            ]
            if len(matches) != 1:
                raise RuntimeError("FastF1 schedule does not contain the requested session")
            session = matches[0]
            if session.capture_until > self.now():
                raise RuntimeError("requested session has not completed")
            self.process_requested(session, job["fixture_stem"])
        except Exception as exc:
            self.remote_queue.finish(
                session_id,
                error="Archive preparation failed on the worker",
            )
            return f"requested archive failed: {session_id}: {type(exc).__name__}"
        finally:
            self.remote_processing.unlink(missing_ok=True)
        return f"requested archive complete: {session_id}"

    def run_once(self) -> str:
        now = self.now()
        state = self.store.load()
        protected = tuple(
            f"{session_id}."
            for session_id, item in state.sessions.items()
            if item.phase in {Phase.RECORDING, Phase.CAPTURED, Phase.PROCESSING}
            or item.retry_phase in {Phase.RECORDING, Phase.PROCESSING}
        )
        cutoff = now.timestamp() - self.config.raw_retention_days * 86_400
        for path in self.config.raw_dir.iterdir():
            if (
                path.is_file()
                and not path.is_symlink()
                and not path.name.startswith(protected)
                and path.stat().st_mtime < cutoff
            ):
                path.unlink()
        years = {now.year}
        if now.month == 12:
            years.add(now.year + 1)
        years.update(int(session_id.split("-", 1)[0]) for session_id in state.sessions)
        refresh = (
            self._schedule_loaded_at is None
            or now - self._schedule_loaded_at >= SCHEDULE_REFRESH
            or self._schedule_years != years
        )
        if refresh:
            refreshed = []
            for year in sorted(years):
                try:
                    refreshed.extend(load_fastf1_schedule(year))
                except Exception:
                    cached = [session for session in self._schedule if session.year == year]
                    if cached:
                        refreshed.extend(cached)
                    elif year == now.year:
                        raise
            self._schedule_loaded_at = now
            self._schedule_years = years
            self._schedule = refreshed
        sessions = self._schedule
        by_id = {session.session_id: session for session in sessions}

        # A crash may happen after the raw file is complete but before CAPTURED
        # is persisted. Resume/finalize RECORDING even after its schedule window.
        for session_id, item in state.sessions.items():
            if item.phase is not Phase.RECORDING:
                continue
            session = by_id.get(session_id)
            if session is None:
                raise RuntimeError(f"schedule no longer contains {session_id}")
            try:
                self.capture(session)
            except Exception as exc:
                retry = self.now() + CAPTURE_RETRY
                self.store.transition(
                    session_id, Phase.FAILED, self.now(), error=str(exc), retry_at=retry,
                )
                return f"capture failed: {session_id}: {exc}"
            self.store.transition(session_id, Phase.CAPTURED, self.now())
            return f"captured: {session_id}"

        # Captured work is always processed first, including after its live window.
        for session_id, item in state.sessions.items():
            due = state.due_phase(session_id, now)
            if item.phase in {Phase.CAPTURED, Phase.PROCESSING}:
                due = Phase.PROCESSING
            if due is not Phase.PROCESSING:
                continue
            session = by_id.get(session_id)
            if session is None:
                raise RuntimeError(f"schedule no longer contains {session_id}")
            self.store.transition(session_id, Phase.PROCESSING, now)
            try:
                self.process(session)
            except Exception as exc:
                retry = self.now() + ARCHIVE_RETRY
                self.store.transition(
                    session_id, Phase.FAILED, self.now(), error=str(exc), retry_at=retry,
                )
                return f"processing failed: {session_id}: {exc}"
            self.store.transition(session_id, Phase.COMPLETE, self.now())
            return f"complete: {session_id}"

        unavailable = {
            session_id
            for session_id, item in state.sessions.items()
            if item.phase is not Phase.RECORDING
            and state.due_phase(session_id, now) is not Phase.RECORDING
        }
        session = select_due_session(sessions, now, unavailable)
        if session is None:
            next_capture = min(
                (
                    item.capture_from
                    for item in sessions
                    if item.capture_from > now
                    and item.session_id not in unavailable
                ),
                default=None,
            )
            if next_capture is not None and next_capture <= now + REMOTE_CAPTURE_GUARD:
                return "idle: scheduled capture is approaching"
            return self._run_remote_once()
        self.store.transition(session.session_id, Phase.RECORDING, now)
        try:
            self.capture(session)
        except Exception as exc:
            retry = self.now() + CAPTURE_RETRY
            self.store.transition(
                session.session_id, Phase.FAILED, self.now(), error=str(exc), retry_at=retry,
            )
            return f"capture failed: {session.session_id}: {exc}"
        self.store.transition(session.session_id, Phase.CAPTURED, self.now())
        return f"captured: {session.session_id}"

    def run_forever(self) -> None:
        while True:
            self._beat()
            try:
                print(f"{self.now().isoformat()} {self.run_once()}", flush=True)
            except Exception as exc:
                print(f"{self.now().isoformat()} worker error: {exc}", file=sys.stderr, flush=True)
            self._beat()
            self.sleep(self.config.interval_seconds)


def main() -> None:
    Recorder(Config.from_env()).run_forever()


if __name__ == "__main__":
    main()
