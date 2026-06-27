"""OpenF1 → normalized events.

Second independent data source: https://api.openf1.org/v1/
No API key required. Produces the same Event envelope as fastf1_adapter.

Usage::

    from racelens.adapters.openf1_adapter import find_session, ingest_openf1

    session_key = find_session(2024, "Monaco")
    events = ingest_openf1(session_key)

Incremental usage (for live polling — reduces per-poll API load)::

    from racelens.adapters.openf1_adapter import OpenF1IncrementalIngester

    ingester = OpenF1IncrementalIngester(session_key)
    events = ingester.fetch()   # first call: full fetch
    events = ingester.fetch()   # subsequent: only new rows since last fetch
"""
from __future__ import annotations

import contextlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from racelens.adapters._common import message_to_status
from racelens.events.models import Event, event

_BASE = "https://api.openf1.org/v1"
_TIMEOUT = 30
_MAX_RETRIES = 4
# OpenF1's free tier limits to 3 req/s and 30 req/min. When exceeded it throttles
# with 429 — and, when sustained, with 401 (it has NO real auth, so a 401 here can
# only mean "you're throttled, back off"). It also 502/503/504s under load. All
# transient → retry with exponential backoff; other 4xx (404) are real errors.
_RETRYABLE_STATUS = {401, 429, 500, 502, 503, 504}
_BACKOFF_BASE_S = 1.5


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(path: str, params: dict[str, Any] | None = None) -> list[dict]:
    """GET JSON from OpenF1 with exponential-backoff retries on rate-limit /
    transient server errors (429, 502, 503, 504) and network errors."""
    url = _BASE + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as exc:
            # Honour Retry-After if present, else exponential backoff. Only retry
            # transient statuses; real 4xx (404 etc.) raise immediately.
            if exc.code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = float(retry_after) if retry_after else _BACKOFF_BASE_S * (2 ** attempt)
                except ValueError:
                    wait = _BACKOFF_BASE_S * (2 ** attempt)
                time.sleep(min(wait, 20))
                continue
            raise
        except (urllib.error.URLError, OSError):
            # Network-level errors may be transient — back off and retry.
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE_S * (2 ** attempt))
                continue
            raise
    return []


# ── Session lookup ────────────────────────────────────────────────────────────

def find_session(year: int, country_or_circuit: str, session_name: str = "Race") -> int:
    """Return OpenF1 session_key for the given year / location / session type.

    Matches on country_name or circuit_short_name (case-insensitive substring).
    """
    rows = _get("/sessions", {"year": year, "session_name": session_name})
    needle = country_or_circuit.lower()
    for row in rows:
        if (needle in str(row.get("country_name", "")).lower()
                or needle in str(row.get("circuit_short_name", "")).lower()
                or needle in str(row.get("location", "")).lower()):
            return int(row["session_key"])
    available = sorted({str(row.get("country_name", "")) for row in rows if row.get("country_name")})
    raise ValueError(
        f"No OpenF1 session found for year={year}, location={country_or_circuit!r}, "
        f"session_name={session_name!r}. "
        f"Available countries: {available if available else '(none — check year/session_name)'}"
    )


# ── Time helpers ──────────────────────────────────────────────────────────────

def _parse_iso(s: str | None) -> float | None:
    """Parse ISO-8601 string → POSIX timestamp (float seconds). Returns None on failure."""
    if not s:
        return None
    # Normalise: replace +HH:MM / -HH:MM suffix or Z to make it UTC-aware
    s_norm = s.strip()
    # Handle timezone offset like +00:00 or -05:30
    if s_norm.endswith("Z"):
        s_norm = s_norm[:-1]
        tz = timezone.utc
    elif len(s_norm) > 6 and s_norm[-6] in ("+", "-") and s_norm[-3] == ":":
        sign = 1 if s_norm[-6] == "+" else -1
        try:
            offset_h = int(s_norm[-5:-3])
            offset_m = int(s_norm[-2:])
            from datetime import timedelta
            tz = timezone(timedelta(minutes=sign * (offset_h * 60 + offset_m)))
        except ValueError:
            tz = timezone.utc
        s_norm = s_norm[:-6]
    else:
        tz = timezone.utc

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s_norm, fmt).replace(tzinfo=tz)
            return dt.timestamp()
        except ValueError:
            continue
    return None


# ── Flag → session status mapping (shared with fastf1_adapter via _common) ────

_FLAG_MAP = {
    "RED": "red_flag",
    "SAFETY CAR": "safety_car",
    "VIRTUAL SAFETY CAR": "vsc",
    "GREEN": "started",
    "CHEQUERED": "finished",
}


def _flag_to_status(flag: str) -> str | None:
    """Map OpenF1 short flag values (e.g. "CHEQUERED") to session status strings."""
    return _FLAG_MAP.get(flag.upper())


# ── Shared row→Event transform ────────────────────────────────────────────────
# This is the single source of truth. ingest_openf1() and
# OpenF1IncrementalIngester both call it with their accumulated row sets.

def _rows_to_events(
    session_key: int,
    driver_rows: list[dict],
    session_rows: list[dict],
    lap_rows: list[dict],
    pos_rows: list[dict],
    pit_rows: list[dict],
    stint_rows: list[dict],
    interval_rows: list[dict],
    rc_rows: list[dict],
) -> list[Event]:
    """Convert raw OpenF1 row sets into a sorted Event list.

    All eight raw row lists are consumed in one pass.  The result is
    deterministic: identical accumulated inputs always produce identical outputs.
    This function has no side effects and does not call the network.
    """
    src = "openf1"
    events: list[Event] = []
    seq = 0  # monotonic ingest_seq counter

    def mk(sid: str, type_: str, t_ms: int, drv: str | None = None,
           lap: int | None = None, **kw) -> Event:
        nonlocal seq
        e = event(sid, type_, t_ms, drv, lap=lap, source=src, **kw)
        e.ingest_seq = seq
        seq += 1
        return e

    # ── Drivers ──────────────────────────────────────────────────────────────
    driver_map: dict[int, str] = {}
    for row in driver_rows:
        dn = row.get("driver_number")
        acronym = row.get("name_acronym") or row.get("broadcast_name") or str(dn)
        if dn is not None:
            driver_map[int(dn)] = str(acronym)

    # ── Session metadata → derive session_id ─────────────────────────────────
    if session_rows:
        s = session_rows[0]
        year = s.get("year", "unknown")
        location = str(s.get("location") or s.get("country_name") or "unknown").lower().replace(" ", "_")
        session_name = str(s.get("session_name") or "race").lower().replace(" ", "_")
    else:
        year = "unknown"
        location = "unknown"
        session_name = "race"
    sid = f"{year}_{location}_{session_name}"

    events.append(mk(sid, "SessionStarted", 0))

    # ── Laps → LapCompleted, compute t0 (rebase anchor) ─────────────────────
    # t0: earliest date_start of lap 1 across all drivers (POSIX seconds)
    t0_posix: float | None = None
    for row in lap_rows:
        if row.get("lap_number") == 1 and row.get("date_start"):
            ts = _parse_iso(row["date_start"])
            if ts is not None and (t0_posix is None or ts < t0_posix):
                t0_posix = ts

    def to_ms(posix: float) -> int:
        return max(0, round((posix - (t0_posix or 0)) * 1000))

    for row in lap_rows:
        dn = row.get("driver_number")
        drv = driver_map.get(int(dn), str(dn)) if dn is not None else None
        lap_no = row.get("lap_number")
        if lap_no is None:
            continue
        lap_no = int(lap_no)

        duration = row.get("lap_duration")
        date_start = _parse_iso(row.get("date_start"))

        # Session time = end of lap = start + duration
        if date_start is not None and duration is not None:
            try:
                t_end_ms = to_ms(date_start + float(duration))
            except (TypeError, ValueError):
                t_end_ms = None
        elif date_start is not None:
            t_end_ms = to_ms(date_start)
        else:
            t_end_ms = None

        if t_end_ms is None:
            continue

        lap_time_ms: int | None = None
        if duration is not None:
            with contextlib.suppress(TypeError, ValueError):
                lap_time_ms = round(float(duration) * 1000)

        events.append(mk(sid, "LapCompleted", t_end_ms, drv, lap=lap_no,
                         lap_time_ms=lap_time_ms))

    # ── Position → PositionChanged (real changes only) ───────────────────────
    last_pos: dict[str, int] = {}  # driver → last seen position
    for row in pos_rows:
        dn = row.get("driver_number")
        drv = driver_map.get(int(dn), str(dn)) if dn is not None else None
        pos = row.get("position")
        if pos is None or drv is None:
            continue
        pos = int(pos)
        ts = _parse_iso(row.get("date"))
        if ts is None:
            continue
        t_ms = to_ms(ts)
        if last_pos.get(drv) != pos:
            last_pos[drv] = pos
            events.append(mk(sid, "PositionChanged", t_ms, drv, position=pos))

    # ── Pits → PitIn / PitOut ────────────────────────────────────────────────
    for row in pit_rows:
        dn = row.get("driver_number")
        drv = driver_map.get(int(dn), str(dn)) if dn is not None else None
        lap_no = int(row["lap_number"]) if row.get("lap_number") is not None else None
        pit_duration = row.get("pit_duration")
        date = _parse_iso(row.get("date"))
        if date is None:
            continue
        t_in_ms = to_ms(date)
        events.append(mk(sid, "PitIn", t_in_ms, drv, lap=lap_no,
                         pit_duration_s=float(pit_duration) if pit_duration else None))
        if pit_duration is not None:
            try:
                t_out_ms = to_ms(date + float(pit_duration))
                events.append(mk(sid, "PitOut", t_out_ms, drv, lap=lap_no))
            except (TypeError, ValueError):
                pass

    # ── Stints → TyreStintUpdated ─────────────────────────────────────────────
    for row in stint_rows:
        dn = row.get("driver_number")
        drv = driver_map.get(int(dn), str(dn)) if dn is not None else None
        compound = row.get("compound")
        tyre_age = row.get("tyre_age_at_start")
        lap_start = row.get("lap_start")

        if compound is None:
            continue

        # Use lap_start to anchor t (best approximation without exact timestamp)
        # We'll look up the earliest LapCompleted time for this driver on lap_start
        # If lap_start == 1, t = 0 (pre-race); otherwise find it from laps
        if lap_start == 1:
            t_ms = 0
        else:
            # Find the LapCompleted for previous lap from lap_rows for this driver
            t_ms = 0
            ref_lap = (lap_start or 1) - 1
            for lr in lap_rows:
                if (lr.get("driver_number") == dn and lr.get("lap_number") == ref_lap):
                    ds = _parse_iso(lr.get("date_start"))
                    dur = lr.get("lap_duration")
                    if ds is not None and dur is not None:
                        with contextlib.suppress(TypeError, ValueError):
                            t_ms = to_ms(ds + float(dur))
                    break

        events.append(mk(sid, "TyreStintUpdated", t_ms, drv,
                         lap=int(lap_start) if lap_start else None,
                         compound=str(compound),
                         age_laps=int(tyre_age) if tyre_age is not None else 0))

    # ── Intervals → GapUpdated / IntervalUpdated (sampled ≤ 1 per driver / 30 s) ──
    last_interval_t: dict[str, int] = {}  # driver → last emitted session_time_ms
    # Track the last valid row seen per driver so we can emit a final sample.
    last_interval_row: dict[str, tuple[int, Any, Any]] = {}  # driver → (t_ms, gap, interval)
    _INTERVAL_SAMPLE_MS = 30_000

    def _parse_gap_value(x: Any) -> float | None:
        """Parse a gap/interval value: numeric, "+N.NNN", or "+N LAP" formats.

        Returns None for non-numeric values such as "+1 LAP".
        Negative values (e.g. leader or timing artefacts) are valid and returned.
        """
        if x is None:
            return None
        s = str(x).lstrip("+")
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    for row in interval_rows:
        dn = row.get("driver_number")
        drv = driver_map.get(int(dn), str(dn)) if dn is not None else None
        if drv is None:
            continue
        date = _parse_iso(row.get("date"))
        if date is None:
            continue
        t_ms = to_ms(date)

        gap = _parse_gap_value(row.get("gap_to_leader"))
        interval = _parse_gap_value(row.get("interval"))

        # Record last valid row for this driver (for end-of-stream flush)
        if gap is not None or interval is not None:
            last_interval_row[drv] = (t_ms, gap, interval)

        # Sampling gate
        if t_ms - last_interval_t.get(drv, -_INTERVAL_SAMPLE_MS) < _INTERVAL_SAMPLE_MS:
            continue
        last_interval_t[drv] = t_ms

        if gap is not None:
            events.append(mk(sid, "GapUpdated", t_ms, drv, gap_s=round(gap, 3)))
        if interval is not None:
            events.append(mk(sid, "IntervalUpdated", t_ms, drv, interval_s=round(interval, 3)))

    # Emit final measurement for each driver if it was not the last sampled point
    for drv, (t_ms, gap, interval) in last_interval_row.items():
        if last_interval_t.get(drv) != t_ms:
            if gap is not None:
                events.append(mk(sid, "GapUpdated", t_ms, drv, gap_s=round(gap, 3)))
            if interval is not None:
                events.append(mk(sid, "IntervalUpdated", t_ms, drv, interval_s=round(interval, 3)))

    # ── Race control → RaceControlMessage + SessionStatusChanged ─────────────
    for row in rc_rows:
        date = _parse_iso(row.get("date"))
        if date is None:
            continue
        t_ms = to_ms(date)
        message = str(row.get("message") or "")
        category = str(row.get("category") or "")
        flag = str(row.get("flag") or "")

        events.append(mk(sid, "RaceControlMessage", t_ms,
                         category=category, message=message, flag=flag))

        # Try message text first (for descriptive messages), then flag field
        status: str | None = message_to_status(message)
        if status is None:
            status = _flag_to_status(flag)
        if status:
            events.append(mk(sid, "SessionStatusChanged", t_ms, status=status))

    # TODO(live-map): OpenF1 /location endpoint streams X/Y car positions at ~3.7 Hz
    # during a live session.  Ingest that here to replace dead-reckoning in the
    # live-map view with real position data.  Endpoint:
    #   GET /location?session_key=<key>  → [{driver_number, date, x, y, z}, ...]
    # Suggested event type: CarPosition(t_ms, driver, x, y).
    # Sample at ~1 Hz for the replay engine (native 3.7 Hz would flood _all).

    # ── Assign ingest_seq and sort ────────────────────────────────────────────
    # ingest_seq is already assigned in creation order (arrival order)
    events.sort(key=lambda e: (e.session_time_ms, e.event_id))
    return events


# ── Main ingestion (full fetch — unchanged public API) ────────────────────────

def ingest_openf1(session_key: int) -> list[Event]:
    """Fetch all relevant endpoints for *session_key* and return normalized Events.

    The session_id is derived deterministically so event_ids match across re-runs.
    This always fetches the complete session data (no incremental state).
    For live polling use OpenF1IncrementalIngester instead.
    """
    driver_rows = _get("/drivers", {"session_key": session_key}) or []
    session_rows = _get("/sessions", {"session_key": session_key}) or []
    lap_rows = _get("/laps", {"session_key": session_key}) or []
    pos_rows = _get("/position", {"session_key": session_key}) or []
    pit_rows = _get("/pit", {"session_key": session_key}) or []
    stint_rows = _get("/stints", {"session_key": session_key}) or []
    interval_rows = _get("/intervals", {"session_key": session_key}) or []
    rc_rows = _get("/race_control", {"session_key": session_key}) or []

    return _rows_to_events(
        session_key,
        driver_rows,
        session_rows,
        lap_rows,
        pos_rows,
        pit_rows,
        stint_rows,
        interval_rows,
        rc_rows,
    )


# ── Incremental ingester for live polling ─────────────────────────────────────

# Time-series endpoints that support the date>= filter for incremental fetching.
# Static endpoints (/drivers, /sessions) only need fetching once.
_TIMESERIES_ENDPOINTS = ("/laps", "/position", "/pit", "/stints", "/intervals", "/race_control")

# The date field name per endpoint (the field used for date>= filtering AND for
# tracking the latest row we've seen).
_DATE_FIELD: dict[str, str] = {
    "/laps": "date_start",
    "/position": "date",
    "/pit": "date",
    "/stints": "date_start",   # stints don't always have date_start; see note below
    "/intervals": "date",
    "/race_control": "date",
}


def _latest_date(rows: list[dict], date_field: str) -> str | None:
    """Return the lexicographically latest ISO date string seen in *rows*."""
    latest: str | None = None
    for row in rows:
        d = row.get(date_field)
        if d and isinstance(d, str):
            if latest is None or d > latest:
                latest = d
    return latest


class OpenF1IncrementalIngester:
    """Stateful ingester that only fetches new rows on each call after the first.

    Design:
    - First call: full fetch (equivalent to ingest_openf1).
    - Subsequent calls: for each time-series endpoint, only request rows with
      ``date>`` the latest date seen so far; static endpoints (/drivers,
      /sessions) are fetched once and reused.
    - Raw rows are accumulated across polls.  Each call re-runs the full
      _rows_to_events() transform over ALL accumulated rows so the replay
      engine always gets a complete, deterministic event list.

    The ``fetch()`` return value is byte-for-byte identical to what
    ``ingest_openf1()`` would return given the same accumulated rows.
    """

    def __init__(self, session_key: int) -> None:
        self._session_key = session_key
        self._initialized = False

        # Accumulated raw rows per endpoint
        self._driver_rows: list[dict] = []
        self._session_rows: list[dict] = []
        self._lap_rows: list[dict] = []
        self._pos_rows: list[dict] = []
        self._pit_rows: list[dict] = []
        self._stint_rows: list[dict] = []
        self._interval_rows: list[dict] = []
        self._rc_rows: list[dict] = []

        # Latest date seen per time-series endpoint (for date>= filter)
        self._latest: dict[str, str | None] = {ep: None for ep in _TIMESERIES_ENDPOINTS}

    def _update_latest(self, endpoint: str, new_rows: list[dict]) -> None:
        """Update the latest-date bookmark for *endpoint* from *new_rows*."""
        date_field = _DATE_FIELD.get(endpoint)
        if date_field is None:
            return
        latest = _latest_date(new_rows, date_field)
        if latest is not None:
            prev = self._latest.get(endpoint)
            if prev is None or latest > prev:
                self._latest[endpoint] = latest

    def _fetch_timeseries(self, endpoint: str) -> list[dict]:
        """Fetch rows for a time-series endpoint, using date> filter after first call."""
        params: dict[str, Any] = {"session_key": self._session_key}
        prev_latest = self._latest.get(endpoint)
        if self._initialized and prev_latest is not None:
            # OpenF1 accepts "date>=" as a literal param key name.
            # Use strictly-greater-than to avoid re-fetching the last row.
            params["date>"] = prev_latest
        return _get(endpoint, params) or []

    def fetch(self) -> list[Event]:
        """Fetch (incrementally after first call) and return the full event list.

        Returns the same result as ingest_openf1() for the same total data set.
        """
        if not self._initialized:
            # First call: full fetch for all endpoints including static ones
            self._driver_rows = _get("/drivers", {"session_key": self._session_key}) or []
            self._session_rows = _get("/sessions", {"session_key": self._session_key}) or []
        # Always re-fetch time-series endpoints (full on first call, incremental thereafter)
        for endpoint, store_attr in (
            ("/laps", "_lap_rows"),
            ("/position", "_pos_rows"),
            ("/pit", "_pit_rows"),
            ("/stints", "_stint_rows"),
            ("/intervals", "_interval_rows"),
            ("/race_control", "_rc_rows"),
        ):
            new_rows = self._fetch_timeseries(endpoint)
            if new_rows:
                # Append new rows; update bookmark
                getattr(self, store_attr).extend(new_rows)
                self._update_latest(endpoint, new_rows)

        self._initialized = True

        return _rows_to_events(
            self._session_key,
            self._driver_rows,
            self._session_rows,
            self._lap_rows,
            self._pos_rows,
            self._pit_rows,
            self._stint_rows,
            self._interval_rows,
            self._rc_rows,
        )
