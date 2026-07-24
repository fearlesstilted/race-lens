"""Small persistent queue for user-requested replay preparation."""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Iterator

SESSION_ID = re.compile(r"^\d{4}-\d{2}-(?:fp[123]|sq|sprint|q|r)$")
_MAX_RECORD_BYTES = 16 * 1024
_ACTIVE = {"queued", "running"}


class QueueFullError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class PreparationQueue:
    """One atomic JSON record per canonical session.

    A session ID is also its job ID, so duplicate submissions cannot create
    duplicate work. ``claim``/``finish`` are the worker-facing half of the
    contract; the API only needs ``get`` and ``enqueue``.
    """

    def __init__(self, directory: Path, max_jobs: int = 32) -> None:
        self.directory = directory
        self.max_jobs = max(1, min(max_jobs, 1000))
        self._thread_lock = Lock()

    @staticmethod
    def _check_session_id(session_id: str) -> None:
        if not SESSION_ID.fullmatch(session_id):
            raise ValueError("invalid canonical session ID")

    def _path(self, session_id: str) -> Path:
        self._check_session_id(session_id)
        return self.directory / f"{session_id}.json"

    def _read(self, path: Path) -> dict | None:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        try:
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode) or details.st_size > _MAX_RECORD_BYTES:
                raise ValueError(f"unsafe preparation record: {path.name}")
            with os.fdopen(fd, encoding="utf-8") as handle:
                fd = -1
                value = json.load(handle)
        finally:
            if fd >= 0:
                os.close(fd)
        if not isinstance(value, dict):
            raise ValueError(f"invalid preparation record: {path.name}")
        return value

    def _write(self, record: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        if len(payload.encode()) > _MAX_RECORD_BYTES:
            raise ValueError("preparation record is too large")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.directory,
                prefix=".preparation-",
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(str(record["session_id"])))
            temporary = None
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            lock_fd = os.open(
                self.directory / ".lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
            )
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    def get(self, session_id: str) -> dict | None:
        return self._read(self._path(session_id))

    def enqueue(self, session_id: str, fixture_stem: str) -> tuple[dict, bool]:
        self._check_session_id(session_id)
        if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", fixture_stem):
            raise ValueError("invalid fixture stem")
        with self._locked():
            existing = self.get(session_id)
            if existing is not None:
                if existing.get("status") == "failed":
                    existing.update(
                        status="queued",
                        updated_at=_now(),
                        replay_session_id=None,
                        error=None,
                    )
                    self._write(existing)
                    return existing, True
                return existing, False
            # Count terminal records too: the filesystem queue has a hard upper
            # bound even if every job fails. Operators can archive/delete old
            # records before accepting more work.
            if sum(1 for _ in self.directory.glob("*.json")) >= self.max_jobs:
                raise QueueFullError("preparation queue is full")
            now = _now()
            record = {
                "job_id": session_id,
                "session_id": session_id,
                "fixture_stem": fixture_stem,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "replay_session_id": None,
                "error": None,
            }
            self._write(record)
            return record, True

    def claim(self, session_id: str) -> dict | None:
        """Atomically mark one queued record running for an external worker."""
        with self._locked():
            record = self.get(session_id)
            if record is None or record.get("status") != "queued":
                return None
            record["status"] = "running"
            record["updated_at"] = _now()
            self._write(record)
            return record

    def finish(
        self,
        session_id: str,
        *,
        replay_session_id: str | None = None,
        error: str | None = None,
    ) -> dict:
        with self._locked():
            record = self.get(session_id)
            if record is None:
                raise KeyError(session_id)
            record["status"] = "failed" if error else "ready"
            record["updated_at"] = _now()
            record["replay_session_id"] = replay_session_id
            record["error"] = error[:500] if error else None
            self._write(record)
            return record
