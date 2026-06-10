"""OpenF1 → normalized events.

Second independent data source: https://api.openf1.org/v1/
No API key required. Produces the same Event envelope as fastf1_adapter.

Usage::

    from racelens.adapters.openf1_adapter import find_session, ingest_openf1

    session_key = find_session(2024, "Monaco")
    events = ingest_openf1(session_key)
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from racelens.adapters._common import STATUS_TABLE as _STATUS, message_to_status
from racelens.events.models import Event, event

_BASE = "https://api.openf1.org/v1"
_TIMEOUT = 30
_MAX_RETRIES = 1


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(path: str, params: dict[str, Any] | None = None) -> list[dict]:
    """GET JSON from OpenF1 with one retry on network error."""
    url = _BASE + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError:
            # HTTP-level errors (4xx/5xx) are not transient — don't retry.
            raise
        except (urllib.error.URLError, OSError):
            # Network-level errors may be transient — retry once.
            if attempt < _MAX_RETRIES:
                time.sleep(1)
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
    # Fallback: return the first result for the year/session if any
    if rows:
        return int(rows[0]["session_key"])
    raise ValueError(
        f"No OpenF1 session found for year={year}, location={country_or_circuit!r}, "
        f"session_name={session_name!r}"
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


# ── Main ingestion ────────────────────────────────────────────────────────────

def ingest_openf1(session_key: int) -> list[Event]:
    """Fetch all relevant endpoints for *session_key* and return normalized Events.

    The session_id is derived deterministically so event_ids match across re-runs.
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
    driver_rows = _get("/drivers", {"session_key": session_key}) or []
    driver_map: dict[int, str] = {}
    for row in driver_rows:
        dn = row.get("driver_number")
        acronym = row.get("name_acronym") or row.get("broadcast_name") or str(dn)
        if dn is not None:
            driver_map[int(dn)] = str(acronym)

    # ── Session metadata → derive session_id ─────────────────────────────────
    session_rows = _get("/sessions", {"session_key": session_key}) or []
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
    lap_rows = _get("/laps", {"session_key": session_key}) or []

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
            try:
                lap_time_ms = round(float(duration) * 1000)
            except (TypeError, ValueError):
                pass

        events.append(mk(sid, "LapCompleted", t_end_ms, drv, lap=lap_no,
                         lap_time_ms=lap_time_ms))

    # ── Position → PositionChanged (real changes only) ───────────────────────
    pos_rows = _get("/position", {"session_key": session_key}) or []
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
    pit_rows = _get("/pit", {"session_key": session_key}) or []
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
    stint_rows = _get("/stints", {"session_key": session_key}) or []
    for row in stint_rows:
        dn = row.get("driver_number")
        drv = driver_map.get(int(dn), str(dn)) if dn is not None else None
        compound = row.get("compound")
        tyre_age = row.get("tyre_age_at_start")
        lap_start = row.get("lap_start")
        lap_end = row.get("lap_end")

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
                        try:
                            t_ms = to_ms(ds + float(dur))
                        except (TypeError, ValueError):
                            pass
                    break

        events.append(mk(sid, "TyreStintUpdated", t_ms, drv,
                         lap=int(lap_start) if lap_start else None,
                         compound=str(compound),
                         age_laps=int(tyre_age) if tyre_age is not None else 0))

    # ── Intervals → GapUpdated / IntervalUpdated (sampled ≤ 1 per driver / 30 s) ──
    interval_rows = _get("/intervals", {"session_key": session_key}) or []
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
    rc_rows = _get("/race_control", {"session_key": session_key}) or []
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

    # ── Assign ingest_seq and sort ────────────────────────────────────────────
    # ingest_seq is already assigned in creation order (arrival order)
    events.sort(key=lambda e: (e.session_time_ms, e.event_id))
    return events
