"""Direct F1 SignalR feed → Event adapter (no fastf1 session reconstruction).

fastf1's livedata path cannot build laps from a live/mid-join recording (it
drops keyframes and its lap builder needs archive-grade data), so for LIVE we
map the raw recorded feed lines to our Event timeline ourselves. The recording
is what `fastf1.livetiming.client.SignalRClient` writes: one python-ish list
per line — [category, payload, iso_timestamp] — where keyframes (subscribe
snapshots) carry payload as a JSON string and an EMPTY timestamp, while live
increments carry payload as a dict and a real timestamp.

Post-session replays keep using the fastf1 adapter (archives parse fine);
this adapter's job is the live tower: positions, gaps, laps, pits, status.
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterator

from racelens.adapters._common import message_to_status
from racelens.events.models import Event, event

# SessionStatus.Status → our SessionStatusChanged payload status
_STATUS_MAP = {
    "Started": "started",
    "Finished": "finished",
    "Ends": "finished",
    "Finalised": "finished",
    "Aborted": "red_flag",
}

_LAPTIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2})\.(\d{3})$")


def _parse_iso(ts: str) -> float | None:
    """ISO UTC timestamp → posix seconds. Feed uses varying precision."""
    ts = ts.strip()
    if not ts:
        return None
    ts = ts.removesuffix("Z")
    # normalize fractional part to 6 digits (feed emits 1..7)
    if "." in ts:
        head, frac = ts.split(".", 1)
        ts = f"{head}.{frac[:6].ljust(6, '0')}"
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _parse_laptime_ms(value: str | None) -> int | None:
    if not value:
        return None
    m = _LAPTIME_RE.match(value.strip())
    if not m:
        return None
    minutes = int(m.group(1) or 0)
    return (minutes * 60 + int(m.group(2))) * 1000 + int(m.group(3))


def _parse_gap_s(value: Any) -> float | None:
    """'+1.234' → 1.234; lapped ('1L') / markers ('LAP 12') → None."""
    if isinstance(value, dict):
        value = value.get("Value")
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().lstrip("+")
    try:
        return float(v)
    except ValueError:
        return None


def _lines(feed_files: tuple[str, ...]) -> Iterator[tuple[str, Any, str]]:
    """Yield (category, payload-as-dict, ts) for every parseable line."""
    for path in feed_files:
        with open(path, encoding="utf-8-sig") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw.startswith("["):
                    continue
                try:
                    row = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    continue
                if not isinstance(row, list) or len(row) < 3:
                    continue
                cat, payload, ts = row[0], row[1], row[2]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                if isinstance(payload, dict):
                    yield cat, payload, ts


def _find_t0(rows: list[tuple[str, Any, str]]) -> float | None:
    """Session-start posix time: StatusSeries 'Started' (keyframe replays
    history, so this works mid-join), else first live SessionStatus Started,
    else first timestamped line (last resort)."""
    for cat, payload, _ in rows:
        if cat == "SessionData":
            series = payload.get("StatusSeries") or {}
            items = series if isinstance(series, list) else series.values()
            for item in items:
                if isinstance(item, dict) and item.get("SessionStatus") == "Started":
                    t = _parse_iso(item.get("Utc") or "")
                    if t is not None:
                        return t
    for cat, payload, ts in rows:
        if cat == "SessionStatus" and payload.get("Status") == "Started":
            t = _parse_iso(ts)
            if t is not None:
                return t
    for _, _, ts in rows:
        t = _parse_iso(ts)
        if t is not None:
            return t
    return None


def ingest_f1live(*feed_files: str, session_id: str = "f1live") -> list[Event]:
    """Map recorded SignalR feed file(s) to the Event timeline.

    Deterministic full-snapshot conversion (LiveRunner's fetch contract):
    same recording → same events; the runner dedupes by event_id across polls.
    """
    rows = list(_lines(feed_files))
    t0 = _find_t0(rows)
    if t0 is None:
        return []

    def to_ms(posix: float) -> int:
        return max(0, round((posix - t0) * 1000))

    join_ms = next(
        (to_ms(ts) for _, _, raw_ts in rows if (ts := _parse_iso(raw_ts)) is not None),
        None,
    )

    # Session badge text ("SILVERSTONE · RACE"): SessionInfo is a keyframe
    # (full history resent on every re-parse), so the first occurrence in the
    # file is stable across polls once the feed has connected.
    session_name: str | None = None
    for cat, payload, _ in rows:
        if cat == "SessionInfo":
            location = (payload.get("Meeting") or {}).get("Location")
            name = payload.get("Name")
            if location and name:
                session_name = f"{location} · {name}".upper()
            break

    sid = session_id
    initial_payload: dict[str, Any] = {}
    if session_name:
        initial_payload["session_name"] = session_name
    events: list[Event] = [event(sid, "SessionStarted", 0, source="f1live", **initial_payload)]

    num_to_abbr: dict[str, str] = {}
    # per-driver last seen values, to emit only real transitions
    pos: dict[str, int] = {}
    laps: dict[str, int] = {}
    in_pit: dict[str, bool] = {}
    last_lap_ms: dict[str, int | None] = {}
    retired: set[str] = set()
    last_status: str | None = None  # dedupe SessionStatus vs RCM-derived statuses
    session_path: str | None = None  # SessionInfo "Path", to build absolute radio audio_url

    def emit_status(status: str, t_ms: int) -> None:
        nonlocal last_status
        if status != last_status:
            last_status = status
            events.append(event(sid, "SessionStatusChanged", t_ms, status=status))

    def drv(num: str) -> str:
        return num_to_abbr.get(num, str(num))

    def apply_driver_list(payload: dict) -> None:
        for num, info in payload.items():
            if isinstance(info, dict) and info.get("Tla"):
                num_to_abbr[str(num)] = str(info["Tla"])

    def apply_timing(lines: dict, t_ms: int) -> None:
        for num, patch in lines.items():
            if not isinstance(patch, dict):
                continue
            d = drv(str(num))

            p = patch.get("Position")
            if p is not None:
                try:
                    p_int = int(p)
                except (TypeError, ValueError):
                    p_int = None
                if p_int is not None and pos.get(d) != p_int:
                    pos[d] = p_int
                    events.append(event(sid, "PositionChanged", t_ms, d, position=p_int))

            if "GapToLeader" in patch:
                gap = _parse_gap_s(patch["GapToLeader"])
                if gap is not None:
                    events.append(event(sid, "GapUpdated", t_ms, d, gap_s=gap))

            if "IntervalToPositionAhead" in patch:
                iv = _parse_gap_s(patch["IntervalToPositionAhead"])
                if iv is not None:
                    events.append(event(sid, "IntervalUpdated", t_ms, d, interval_s=iv))

            if "LastLapTime" in patch:
                lt = patch["LastLapTime"]
                last_lap_ms[d] = _parse_laptime_ms(lt.get("Value") if isinstance(lt, dict) else lt)

            n = patch.get("NumberOfLaps")
            if isinstance(n, int) and n > laps.get(d, 0):
                laps[d] = n
                events.append(event(sid, "LapCompleted", t_ms, d, lap=n,
                                    lap_time_ms=last_lap_ms.get(d)))

            if "InPit" in patch:
                now_in = bool(patch["InPit"])
                was_in = in_pit.get(d)
                if was_in is None or now_in != was_in:
                    in_pit[d] = now_in
                    cur_lap = laps.get(d, 0) + 1  # NumberOfLaps = completed
                    if now_in:
                        events.append(event(sid, "PitIn", t_ms, d, lap=cur_lap))
                    elif was_in:  # only a real out after a seen in
                        events.append(event(sid, "PitOut", t_ms, d, lap=cur_lap))

            # 'Retired' is definitive; 'Stopped' can be a spin-and-continue, so
            # only the explicit flag retires a car. Once per driver.
            if patch.get("Retired") and d not in retired:
                retired.add(d)
                events.append(event(sid, "RetirementDetected", t_ms, d,
                                    lap=laps.get(d, 0) + 1))

    def apply_tyres(lines: dict, t_ms: int) -> None:
        for num, patch in lines.items():
            if not isinstance(patch, dict):
                continue
            stints = patch.get("Stints")
            # Feed duality: keyframes send Stints as a LIST (full history),
            # increments as a DICT of patches. Accept both, else starting
            # compounds are lost on mid-join and TYR stays empty until a stop.
            if isinstance(stints, dict):
                ordered = [
                    stints[key]
                    for key in sorted(
                        stints,
                        key=lambda key: (0, int(key)) if str(key).isdigit() else (1, str(key)),
                    )
                ]
            elif isinstance(stints, list):
                ordered = stints
            else:
                continue
            current = next(
                (stint for stint in reversed(ordered)
                 if isinstance(stint, dict) and stint.get("Compound")),
                None,
            )
            if current:
                events.append(event(
                    sid, "TyreStintUpdated", t_ms, drv(str(num)), source="f1live",
                    compound=str(current["Compound"]).capitalize(),
                    age_laps=int(current.get("TotalLaps") or 0),
                ))

    # Pass 1: driver names from ALL DriverList payloads (keyframes included),
    # so events emitted from early lines already carry abbreviations.
    for cat, payload, _ in rows:
        if cat == "DriverList":
            apply_driver_list(payload)

    # Pass 2: chronological event emission.
    for cat, payload, ts in rows:
        t_posix = _parse_iso(ts)
        if t_posix is None:
            # Keyframe (no timestamp): baseline snapshot. Anchor it at the join
            # moment if known, else at 0 — live views read state_at(latest), so
            # increments supersede it either way.
            t_ms = join_ms if join_ms is not None else 0
        else:
            t_ms = to_ms(t_posix)

        if cat == "SessionInfo":
            path = payload.get("Path")
            if isinstance(path, str) and path:
                session_path = path
        elif cat == "SessionStatus":
            status = _STATUS_MAP.get(str(payload.get("Status")))
            if status:
                emit_status(status, t_ms)
        elif cat == "TimingData":
            lines = payload.get("Lines")
            if isinstance(lines, dict):
                apply_timing(lines, t_ms)
        elif cat == "TimingAppData":
            lines = payload.get("Lines")
            if isinstance(lines, dict):
                apply_tyres(lines, t_ms)
        elif cat == "RaceControlMessages":
            msgs = payload.get("Messages")
            items = msgs.values() if isinstance(msgs, dict) else (msgs or [])
            for m in items:
                if not isinstance(m, dict) or not m.get("Message"):
                    continue
                text = str(m["Message"])
                lap_no = m.get("Lap") if isinstance(m.get("Lap"), int) else None
                events.append(event(sid, "RaceControlMessage", t_ms, lap=lap_no,
                                    category=str(m.get("Category", "")), message=text))
                status = message_to_status(text)
                if status is not None:
                    emit_status(status, t_ms)
        elif cat == "TeamRadio":
            caps = payload.get("Captures")
            items = caps.values() if isinstance(caps, dict) else (caps or [])
            for c in items:
                if not isinstance(c, dict) or not c.get("Path"):
                    continue
                # Keyframes contain the full radio history. Their row timestamp
                # is the join time, not the clip time; each capture carries its
                # own UTC timestamp and must be placed on the replay with that.
                radio_posix = _parse_iso(str(c.get("Utc") or ""))
                radio_ms = to_ms(radio_posix) if radio_posix is not None else t_ms
                d = drv(str(c.get("RacingNumber", "")))
                radio_payload: dict[str, Any] = {
                    "category": "Radio",
                    "message": f"RADIO: {d}",
                    "audio_path": str(c["Path"]),
                }
                if session_path:
                    radio_payload["audio_url"] = (
                        f"https://livetiming.formula1.com/static/{session_path}{c['Path']}"
                    )
                events.append(event(sid, "RaceControlMessage", radio_ms, d,
                                    lap=laps.get(d, 0) + 1,
                                    **radio_payload))

    events.sort(key=lambda e: (e.session_time_ms, e.event_id))
    return events
