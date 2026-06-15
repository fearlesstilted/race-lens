"""Significant race events: timeline markers and highlight foundations.

significant_events() produces a deterministic, spoiler-free list of
high-value moments from a race session. Suitable for timeline markers,
highlight reels, and social summaries.

Deterministic: same events + until_ms → same output, always.
Spoiler-free: only events at or before until_ms are considered.
Testable: pure function, no I/O, no side effects.
"""
from __future__ import annotations

import re
from typing import Any

from racelens.events.models import Event
from racelens.replay.engine import ReplayEngine

# ── Constants ──────────────────────────────────────────────────────────────────

# Kind values
KIND_RED_FLAG = "RED_FLAG"
KIND_SAFETY_CAR = "SAFETY_CAR"
KIND_VSC = "VSC"
KIND_GREEN = "GREEN"
KIND_INCIDENT = "INCIDENT"
KIND_CRASH = "CRASH"
KIND_PENALTY = "PENALTY"
KIND_RETIREMENT = "RETIREMENT"
KIND_LEAD_CHANGE = "LEAD_CHANGE"
KIND_PODIUM_CHANGE = "PODIUM_CHANGE"
KIND_FASTEST_LAP = "FASTEST_LAP"

# Severity levels
SEV_CRITICAL = "critical"
SEV_HIGH = "high"
SEV_MEDIUM = "medium"
SEV_LOW = "low"

# Status → (kind, severity) for SessionStatusChanged
_STATUS_KIND: dict[str, tuple[str, str]] = {
    "red_flag": (KIND_RED_FLAG, SEV_CRITICAL),
    "safety_car": (KIND_SAFETY_CAR, SEV_HIGH),
    "vsc": (KIND_VSC, SEV_HIGH),
}

# "restart" statuses — started after neutralisation
_RESTART_STATUSES = {"started"}

# Words that indicate a collision/contact event rather than generic incident
_CRASH_WORDS = {"COLLISION", "CONTACT", "CRASH", "ACCIDENT"}

# Penalty words in RaceControlMessage text
_PENALTY_WORDS = {"PENALTY", "TIME PENALTY", "DRIVE THROUGH", "STOP AND GO"}
# Investigation words (lower severity)
_INVESTIGATION_WORDS = {"UNDER INVESTIGATION", "NOTED", "WILL BE INVESTIGATED"}


# ── Driver code extraction ─────────────────────────────────────────────────────

# Matches patterns like: CAR 55 (SAI), CARS 55 (SAI) AND 81 (PIA), CAR 10 (GAS)
_DRV_PATTERN = re.compile(r"\(([A-Z]{2,4})\)")


def _extract_drivers(message: str) -> list[str]:
    """Extract driver 3-letter codes from a race control message.

    Handles: "CARS 55 (SAI) AND 81 (PIA)" → ["SAI", "PIA"]
             "CAR 10 (GAS)" → ["GAS"]
    Returns unique drivers in order of appearance.
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in _DRV_PATTERN.finditer(message):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


# ── Text builders ──────────────────────────────────────────────────────────────

def _flag_texts(kind: str) -> tuple[str, str]:
    texts: dict[str, tuple[str, str]] = {
        KIND_RED_FLAG: ("Red flag", "Красный флаг"),
        KIND_SAFETY_CAR: ("Safety car deployed", "Выезд Safety car"),
        KIND_VSC: ("Virtual safety car", "Виртуальный Safety car"),
        KIND_GREEN: ("Race resumed", "Гонка возобновлена"),
    }
    return texts.get(kind, (kind, kind))


def _incident_texts(drivers: list[str], is_crash: bool) -> tuple[str, str]:
    drv_str = " & ".join(drivers) if drivers else "unknown"
    if is_crash:
        en = f"Crash/contact: {drv_str}"
        ru = f"Авария/контакт: {drv_str}"
    else:
        en = f"Incident: {drv_str}"
        ru = f"Инцидент: {drv_str}"
    return en, ru


def _penalty_texts(drivers: list[str], msg_upper: str) -> tuple[str, str]:
    drv_str = drivers[0] if drivers else "?"
    if "5 SECOND" in msg_upper or "5S" in msg_upper:
        penalty_type = "5s penalty"
        ru_type = "Штраф 5с"
    elif "10 SECOND" in msg_upper or "10S" in msg_upper:
        penalty_type = "10s penalty"
        ru_type = "Штраф 10с"
    elif "DRIVE THROUGH" in msg_upper:
        penalty_type = "Drive-through penalty"
        ru_type = "Штраф drive-through"
    elif "STOP AND GO" in msg_upper:
        penalty_type = "Stop & go penalty"
        ru_type = "Штраф stop & go"
    elif "TIME PENALTY" in msg_upper or "PENALTY" in msg_upper:
        penalty_type = "Penalty"
        ru_type = "Штраф"
    elif "UNDER INVESTIGATION" in msg_upper:
        penalty_type = "Under investigation"
        ru_type = "Под расследованием"
    else:
        penalty_type = "Noted"
        ru_type = "Принято к сведению"
    return f"{penalty_type} — {drv_str}", f"{ru_type} — {drv_str}"


def _lead_change_texts(new_leader: str, old_leader: str) -> tuple[str, str]:
    return (
        f"Lead change: {new_leader} passes {old_leader}",
        f"Смена лидера: {new_leader} обходит {old_leader}",
    )


def _podium_change_texts(top3: list[str]) -> tuple[str, str]:
    joined = ", ".join(top3)
    return f"Podium change: {joined}", f"Смена тройки: {joined}"


def _fastest_lap_texts(driver: str, lap_ms: int) -> tuple[str, str]:
    total_s, ms_part = divmod(lap_ms, 1000)
    minutes, secs = divmod(total_s, 60)
    t = f"{minutes}:{secs:02d}.{ms_part:03d}"
    return f"Fastest lap: {driver} {t}", f"Быстрейший круг: {driver} {t}"


# ── Core function ──────────────────────────────────────────────────────────────

def significant_events(
    events: list[Event],
    until_ms: int | None = None,
    state_engine: ReplayEngine | None = None,
) -> list[dict[str, Any]]:
    """Return significant race events up to until_ms.

    Args:
        events: Normalized Event list (from adapter or fixture).
        until_ms: Spoiler cutoff. None means no cutoff (full race).
        state_engine: Pre-built ReplayEngine for classification tracking.
                      If None, one is built from events.

    Returns:
        List of dicts: {at_ms, lap, kind, severity, driver_ids, text_en, text_ru}
        Sorted by at_ms ascending. Deduplicated.
    """
    if until_ms is not None:
        visible = [e for e in events if e.session_time_ms <= until_ms]
    else:
        visible = list(events)

    visible_sorted = sorted(visible, key=lambda e: (e.session_time_ms, e.event_id))

    if not visible_sorted:
        return []

    # Build engine lazily — needed for LEAD/PODIUM/FASTEST tracking
    if state_engine is None:
        state_engine = ReplayEngine(visible)

    markers: list[dict[str, Any]] = []
    seen_ids: set[str] = set()  # deduplicate by event_id

    # ── Track classification state for lead/podium/fastest ────────────────────
    # We iterate LapCompleted events in order and query state at each one.
    prev_leader: str | None = None
    prev_top3: frozenset[str] = frozenset()
    best_race_lap_ms: int | None = None  # absolute fastest lap in race so far

    # Pre-collect classification checkpoints: times where we should sample state.
    # Use all LapCompleted times (de-duped, sorted) for efficiency.
    lap_times: list[int] = sorted(
        {e.session_time_ms for e in visible_sorted if e.type == "LapCompleted"}
    )

    # Initialise from t=0 state (grid)
    if lap_times:
        state0 = state_engine.state_at(0)
        cl0 = state0.get("classification", [])
        prev_leader = cl0[0] if cl0 else None
        prev_top3 = frozenset(cl0[:3]) if len(cl0) >= 3 else frozenset(cl0)

    for t_ms in lap_times:
        state = state_engine.state_at(t_ms)
        cl = state.get("classification", [])
        if not cl:
            continue

        new_leader = cl[0]
        new_top3 = frozenset(cl[:3]) if len(cl) >= 3 else frozenset(cl)

        # LEAD_CHANGE
        if prev_leader is not None and new_leader != prev_leader:
            text_en, text_ru = _lead_change_texts(new_leader, prev_leader)
            _add_marker(
                markers, seen_ids,
                at_ms=t_ms,
                lap=state.get("lap"),
                kind=KIND_LEAD_CHANGE,
                severity=SEV_HIGH,
                driver_ids=[new_leader, prev_leader],
                text_en=text_en,
                text_ru=text_ru,
                dedup_key=f"lc:{t_ms}:{new_leader}:{prev_leader}",
            )

        # PODIUM_CHANGE — only set changes (not internal reshuffles)
        if new_top3 != prev_top3 and len(cl) >= 3:
            top3_ordered = [d for d in cl[:3]]
            text_en, text_ru = _podium_change_texts(top3_ordered)
            _add_marker(
                markers, seen_ids,
                at_ms=t_ms,
                lap=state.get("lap"),
                kind=KIND_PODIUM_CHANGE,
                severity=SEV_MEDIUM,
                driver_ids=top3_ordered,
                text_en=text_en,
                text_ru=text_ru,
                dedup_key=f"pc:{t_ms}:{','.join(sorted(new_top3))}",
            )

        # FASTEST_LAP — new absolute best lap in the race
        drivers_state = state.get("drivers", {})
        for drv, ds in drivers_state.items():
            blap = ds.get("best_lap_ms")
            if blap is not None and (best_race_lap_ms is None or blap < best_race_lap_ms):
                best_race_lap_ms = blap
                text_en, text_ru = _fastest_lap_texts(drv, blap)
                _add_marker(
                    markers, seen_ids,
                    at_ms=t_ms,
                    lap=state.get("lap"),
                    kind=KIND_FASTEST_LAP,
                    severity=SEV_LOW,
                    driver_ids=[drv],
                    text_en=text_en,
                    text_ru=text_ru,
                    dedup_key=f"fl:{t_ms}:{drv}:{blap}",
                )

        prev_leader = new_leader
        prev_top3 = new_top3

    # ── Session status events (flags and restarts) ────────────────────────────
    prev_status: str | None = None
    neutralisation_active = False  # True when red_flag / SC / VSC in effect

    for e in visible_sorted:
        if e.event_id in seen_ids:
            continue
        if e.type != "SessionStatusChanged":
            continue

        status = e.payload.get("status", "")

        if status in _STATUS_KIND:
            kind, severity = _STATUS_KIND[status]
            text_en, text_ru = _flag_texts(kind)
            _add_marker(
                markers, seen_ids,
                at_ms=e.session_time_ms,
                lap=e.lap,
                kind=kind,
                severity=severity,
                driver_ids=[],
                text_en=text_en,
                text_ru=text_ru,
                dedup_key=f"status:{e.event_id}",
            )
            neutralisation_active = True

        elif status in _RESTART_STATUSES and neutralisation_active and prev_status is not None:
            # Race restart after neutralisation
            text_en, text_ru = _flag_texts(KIND_GREEN)
            _add_marker(
                markers, seen_ids,
                at_ms=e.session_time_ms,
                lap=e.lap,
                kind=KIND_GREEN,
                severity=SEV_MEDIUM,
                driver_ids=[],
                text_en=text_en,
                text_ru=text_ru,
                dedup_key=f"green:{e.event_id}",
            )
            neutralisation_active = False

        prev_status = status

    # ── Race control messages: incidents, penalties ───────────────────────────
    for e in visible_sorted:
        if e.event_id in seen_ids:
            continue
        if e.type != "RaceControlMessage":
            continue

        msg = e.payload.get("message", "")
        msg_upper = msg.upper()

        # ── INCIDENT / CRASH ──────────────────────────────────────────────────
        is_incident_msg = "INCIDENT" in msg_upper or "COLLISION" in msg_upper or "CONTACT" in msg_upper

        if is_incident_msg:
            drivers = _extract_drivers(msg)
            is_crash = any(w in msg_upper for w in _CRASH_WORDS)
            kind = KIND_CRASH if is_crash else KIND_INCIDENT
            text_en, text_ru = _incident_texts(drivers, is_crash)
            _add_marker(
                markers, seen_ids,
                at_ms=e.session_time_ms,
                lap=e.lap,
                kind=kind,
                severity=SEV_HIGH,
                driver_ids=drivers,
                text_en=text_en,
                text_ru=text_ru,
                dedup_key=f"incident:{e.event_id}",
            )
            continue

        # ── PENALTY / INVESTIGATION ───────────────────────────────────────────
        has_penalty = any(pw in msg_upper for pw in _PENALTY_WORDS)
        has_investigation = any(iw in msg_upper for iw in _INVESTIGATION_WORDS)

        if has_penalty or has_investigation:
            drivers = _extract_drivers(msg)
            # Severity: penalty = high, investigation/noted = medium
            severity = SEV_HIGH if has_penalty else SEV_MEDIUM
            text_en, text_ru = _penalty_texts(drivers, msg_upper)
            _add_marker(
                markers, seen_ids,
                at_ms=e.session_time_ms,
                lap=e.lap,
                kind=KIND_PENALTY,
                severity=severity,
                driver_ids=drivers,
                text_en=text_en,
                text_ru=text_ru,
                dedup_key=f"penalty:{e.event_id}",
            )

    # TODO: RETIREMENT — reliable detection requires tracking retired flag
    # transitions. The engine marks drivers retired=True after falling >5 laps
    # behind the leader, but this doesn't produce a precise at_ms. Skipping
    # for now; can be added when the engine emits a RetiredFlag event.

    # ── Sort by at_ms, stable ─────────────────────────────────────────────────
    markers.sort(key=lambda m: (m["at_ms"], m["kind"]))
    return markers


# ── Internal helpers ──────────────────────────────────────────────────────────

def _add_marker(
    markers: list[dict[str, Any]],
    seen: set[str],
    *,
    at_ms: int,
    lap: int | None,
    kind: str,
    severity: str,
    driver_ids: list[str],
    text_en: str,
    text_ru: str,
    dedup_key: str,
) -> None:
    """Append a marker if dedup_key not already seen."""
    if dedup_key in seen:
        return
    seen.add(dedup_key)
    markers.append({
        "at_ms": at_ms,
        "lap": lap,
        "kind": kind,
        "severity": severity,
        "driver_ids": driver_ids,
        "text_en": text_en,
        "text_ru": text_ru,
    })
