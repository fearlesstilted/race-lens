#!/usr/bin/env python3
"""Publish recorder staging through an isolated CI-gated capture branch."""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

MAX_FILE_BYTES = 95 * 1024 * 1024
STEM = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=check,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _read_at(directory_fd: int, name: str, limit: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= limit:
            raise ValueError(f"unsafe staged file: {name}")
        chunks = []
        remaining = details.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != details.st_size or os.fstat(descriptor).st_size != details.st_size:
            raise ValueError(f"staged file changed while reading: {name}")
        return data
    finally:
        os.close(descriptor)


def manifest_files(name: str, staging_fd: int) -> tuple[str, list[str]]:
    try:
        data = json.loads(_read_at(staging_fd, name, 64 * 1024))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest: {name}") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"session", "files"}
        or not isinstance(data["session"], str)
        or not isinstance(data["files"], list)
        or not all(isinstance(item, str) for item in data["files"])
    ):
        raise ValueError(f"invalid manifest fields: {name}")
    stem = name.removesuffix(".ready.json")
    expected = {
        f"{stem}.jsonl", f"{stem}.track.json", f"{stem}.positions.json",
    }
    if not STEM.fullmatch(stem) or set(data["files"]) != expected:
        raise ValueError(f"manifest file set is not allowed: {name}")
    for source_name in expected:
        descriptor = os.open(
            source_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=staging_fd,
        )
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_size <= 0
                or details.st_size > MAX_FILE_BYTES
            ):
                raise ValueError(
                    f"staged file size is not allowed: {source_name} ({details.st_size})"
                )
        finally:
            os.close(descriptor)
    return stem, sorted(expected)


def _snapshot_at(staging_fd: int, name: str, destination: Path) -> None:
    source_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=staging_fd)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    target_fd = None
    try:
        details = os.fstat(source_fd)
        if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= MAX_FILE_BYTES:
            raise ValueError(f"unsafe staged file: {name}")
        target_fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
        )
        remaining = details.st_size
        while remaining:
            chunk = os.read(source_fd, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f"staged file shrank while copying: {name}")
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
            remaining -= len(chunk)
        if os.read(source_fd, 1) or os.fstat(source_fd).st_size != details.st_size:
            raise ValueError(f"staged file grew while copying: {name}")
        os.fsync(target_fd)
        os.close(target_fd)
        target_fd = None
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        if target_fd is not None:
            os.close(target_fd)
        os.close(source_fd)
        temporary.unlink(missing_ok=True)


def publish(repo: Path, staging_fd: int, manifest_name: str) -> None:
    stem, sources = manifest_files(manifest_name, staging_fd)
    if git(repo, "status", "--porcelain").stdout.strip():
        raise RuntimeError("publisher checkout is dirty")
    git(repo, "fetch", "origin", "main")
    branch = f"capture/{stem}"
    git(repo, "switch", "-C", branch, "origin/main")
    fixtures = repo / "backend" / "fixtures"
    try:
        destinations = []
        for source_name in sources:
            destination = fixtures / source_name
            _snapshot_at(staging_fd, source_name, destination)
            destinations.append(destination)
        git(repo, "add", "-f", *[str(path) for path in destinations])
        if git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
            git(repo, "commit", "-m", f"data({stem}): publish recorded session")
            git(repo, "push", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}")
        os.rename(
            manifest_name, manifest_name.removesuffix(".json") + ".published",
            src_dir_fd=staging_fd, dst_dir_fd=staging_fd,
        )
    finally:
        git(repo, "switch", "main", check=False)
        git(repo, "pull", "--ff-only", "origin", "main", check=False)


def main() -> None:
    repo = Path(os.environ.get("RACELENS_REPO", Path(__file__).resolve().parents[2])).resolve()
    data = Path(
        os.environ.get(
            "RACELENS_RECORDER_STORAGE",
            Path.home() / ".local" / "share" / "race-lens-recorder",
        )
    ).resolve()
    staging = data / "data" / "publish"
    staging.mkdir(parents=True, exist_ok=True)
    lock_path = data / "publisher.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            manifests = sorted(
                name for name in os.listdir(staging_fd) if name.endswith(".ready.json")
            )
            for manifest_name in manifests:
                publish(repo, staging_fd, manifest_name)
        finally:
            os.close(staging_fd)


if __name__ == "__main__":
    try:
        main()
    except BlockingIOError:
        pass
    except Exception as exc:
        print(f"publisher: {exc}", file=sys.stderr)
        raise SystemExit(1)
