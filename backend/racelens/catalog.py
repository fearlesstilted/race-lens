"""Historical F1 session catalog backed by FastF1 with a Jolpica fallback."""
from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from racelens.recorder.schedule import ScheduledSession, load_fastf1_schedule
from racelens.recorder.worker import fixture_stem

FIRST_SEASON = 2018
JOLPICA_URL = "https://api.jolpi.ca/ergast/f1/{year}.json"
_CACHE_MAX_AGE_S = 24 * 60 * 60
_MAX_SCHEDULE_BYTES = 2 * 1024 * 1024
_SESSION_FIELDS = (
    ("FirstPractice", "FP1"),
    ("SecondPractice", "FP2"),
    ("ThirdPractice", "FP3"),
    ("SprintQualifying", "SQ"),
    ("SprintShootout", "SQ"),
    ("Sprint", "Sprint"),
    ("Qualifying", "Q"),
)
_SESSION_NAMES = {
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
    "SQ": "Sprint Qualifying",
    "Sprint": "Sprint",
    "Q": "Qualifying",
    "R": "Race",
}
_VENUE_ALIASES = {
    "german": "germany",
    "spanish": "spain",
    "british": "silverstone",
}


class CatalogUnavailable(RuntimeError):
    pass


def supported_seasons(now: datetime | None = None) -> list[int]:
    current = (now or datetime.now(UTC)).year
    return list(range(current, FIRST_SEASON - 1, -1))


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, dict):
        return None
    date, clock = value.get("date"), value.get("time")
    if not isinstance(date, str) or not isinstance(clock, str):
        return None
    try:
        parsed = datetime.fromisoformat(f"{date}T{clock}".replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_jolpica(payload: dict, year: int) -> list[ScheduledSession]:
    try:
        races = payload["MRData"]["RaceTable"]["Races"]
    except (KeyError, TypeError):
        raise CatalogUnavailable("Jolpica returned an invalid schedule") from None
    if not isinstance(races, list):
        raise CatalogUnavailable("Jolpica returned an invalid schedule")

    sessions: list[ScheduledSession] = []
    for race in races:
        if not isinstance(race, dict):
            continue
        try:
            round_number = int(race["round"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(race.get("raceName") or f"Round {round_number}")
        seen: set[str] = set()
        for field, kind in _SESSION_FIELDS:
            starts_at = _parse_datetime(race.get(field))
            if starts_at is not None and kind not in seen:
                sessions.append(ScheduledSession(year, round_number, name, kind, starts_at))
                seen.add(kind)
        race_start = _parse_datetime(race)
        if race_start is not None:
            sessions.append(ScheduledSession(year, round_number, name, "R", race_start))
    return sorted(sessions, key=lambda item: (item.starts_at, item.session_id))


def _read_json(path: Path) -> dict | None:
    try:
        if path.stat().st_size > _MAX_SCHEDULE_BYTES:
            return None
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".catalog-", delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(value, handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def load_jolpica_schedule(year: int, cache_dir: Path) -> list[ScheduledSession]:
    """Fetch one fixed-host schedule, falling back to a stale disk cache."""
    if year < FIRST_SEASON or year > datetime.now(UTC).year:
        raise ValueError("unsupported season")
    cache_path = cache_dir / f"jolpica-{year}.json"
    cached = _read_json(cache_path)
    try:
        fresh = cached is not None and time.time() - cache_path.stat().st_mtime < _CACHE_MAX_AGE_S
    except OSError:
        fresh = False
    if fresh:
        return _parse_jolpica(cached, year)

    request = urllib.request.Request(
        JOLPICA_URL.format(year=year),
        headers={"Accept": "application/json", "User-Agent": "race-lens/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read(_MAX_SCHEDULE_BYTES + 1)
        if len(raw) > _MAX_SCHEDULE_BYTES:
            raise ValueError("schedule response is too large")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("response is not an object")
        sessions = _parse_jolpica(payload, year)
        _write_json_atomic(cache_path, payload)
        return sessions
    except (OSError, ValueError, json.JSONDecodeError, CatalogUnavailable) as exc:
        if cached is not None:
            return _parse_jolpica(cached, year)
        raise CatalogUnavailable(f"schedule unavailable for {year}") from exc


def _normalized_schedule(sessions: Iterable[ScheduledSession]) -> dict:
    return {
        "sessions": [
            {
                "year": item.year,
                "round": item.round_number,
                "event": item.event_name,
                "kind": item.kind,
                "starts_at": item.starts_at.isoformat(),
            }
            for item in sessions
        ]
    }


def _parse_normalized_schedule(value: dict | None) -> list[ScheduledSession]:
    if value is None or not isinstance(value.get("sessions"), list):
        raise CatalogUnavailable("cached schedule is invalid")
    try:
        return [
            ScheduledSession(
                int(item["year"]),
                int(item["round"]),
                str(item["event"]),
                str(item["kind"]),
                datetime.fromisoformat(str(item["starts_at"])),
            )
            for item in value["sessions"]
        ]
    except (KeyError, TypeError, ValueError):
        raise CatalogUnavailable("cached schedule is invalid") from None


def load_schedule(year: int, cache_dir: Path) -> list[ScheduledSession]:
    """Prefer FastF1, then Jolpica, then the last normalized disk snapshot."""
    cache_path = cache_dir / f"schedule-{year}.json"
    try:
        sessions = load_fastf1_schedule(year)
    except Exception:
        try:
            sessions = load_jolpica_schedule(year, cache_dir)
        except CatalogUnavailable:
            return _parse_normalized_schedule(_read_json(cache_path))
    try:
        _write_json_atomic(cache_path, _normalized_schedule(sessions))
    except OSError:
        pass
    return sessions


def public_job(record: dict) -> dict:
    status = "processing" if record["status"] == "running" else record["status"]
    return {
        "job_id": record["job_id"],
        "session_id": record["session_id"],
        "status": status,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "replay_session_id": record.get("replay_session_id"),
        "error": (
            "Archive preparation failed; retry to try again"
            if status == "failed"
            else "Archive preparation will retry automatically"
            if record.get("error")
            else None
        ),
    }


def catalog_session(
    session: ScheduledSession,
    fixtures_dir: Path,
    queue: Any,
) -> dict:
    expected_id = fixture_stem(session)
    venue, suffix = expected_id.split(f"_{session.year}_", 1)
    candidates = [expected_id]
    if venue in _VENUE_ALIASES:
        candidates.append(f"{_VENUE_ALIASES[venue]}_{session.year}_{suffix}")
    replay_id = next(
        (item for item in candidates if (fixtures_dir / f"{item}.jsonl").is_file()),
        expected_id,
    )
    if (fixtures_dir / f"{replay_id}.jsonl").is_file():
        status, job_id = "ready", None
    else:
        record = queue.get(session.session_id)
        status = (
            "processing" if record and record.get("status") in {"processing", "running"}
            else "queued" if record and record.get("status") == "queued"
            else "failed" if record and record.get("status") == "failed"
            else "ready" if record and record.get("status") == "ready"
            else "prepare"
        )
        job_id = session.session_id if record else None
        if status != "ready":
            replay_id = None
        elif record:
            replay_id = record.get("replay_session_id") or replay_id
    return {
        "session_id": session.session_id,
        "type": session.kind,
        "name": _SESSION_NAMES[session.kind],
        "starts_at": session.starts_at.isoformat().replace("+00:00", "Z"),
        "status": status,
        "replay_session_id": replay_id,
        "job_id": job_id,
    }


def build_catalog(
    season: int,
    fixtures_dir: Path,
    queue: Any,
    cache_dir: Path,
    *,
    preparation_enabled: bool,
    now: datetime | None = None,
) -> dict:
    current = now or datetime.now(UTC)
    try:
        sessions: Iterable[ScheduledSession] = load_schedule(season, cache_dir)
        available = True
    except CatalogUnavailable:
        sessions = ()
        available = False

    events: dict[tuple[int, str], list[dict]] = {}
    for session in sessions:
        if session.capture_until > current:
            continue
        key = (session.round_number, session.event_name)
        events.setdefault(key, []).append(catalog_session(session, fixtures_dir, queue))
    return {
        "season": season,
        "seasons": supported_seasons(current),
        "catalog_available": available,
        "preparation_enabled": preparation_enabled,
        "events": [
            {"round": round_number, "name": name, "sessions": items}
            for (round_number, name), items in sorted(events.items())
        ],
    }


def find_session(catalog: dict, session_id: str) -> tuple[dict, dict] | None:
    for event in catalog["events"]:
        for session in event["sessions"]:
            if session["session_id"] == session_id:
                return event, session
    return None


def expected_replay_id(season: int, event: dict, session: dict) -> str:
    starts_at = datetime.fromisoformat(session["starts_at"].replace("Z", "+00:00"))
    scheduled = ScheduledSession(
        season, int(event["round"]), str(event["name"]), str(session["type"]), starts_at,
    )
    return fixture_stem(scheduled)


def ready_job(session_id: str, replay_session_id: str, path: Path) -> dict:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
    return {
        "job_id": session_id,
        "session_id": session_id,
        "status": "ready",
        "created_at": stamp,
        "updated_at": stamp,
        "replay_session_id": replay_session_id,
        "error": None,
    }
