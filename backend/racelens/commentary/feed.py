"""Event feed for the frontend: spoiler-free, newest-first, human-readable.

render_feed() converts raw normalized events into a compact list suitable for
a live-ticker UI. Only meaningful event types are included; noise (position
changes, gaps, intervals) is suppressed.
"""
from __future__ import annotations

import bisect
from typing import Any

from racelens.events.models import Event

# Compound display names — handle both full names and abbreviations
_COMPOUND_EN = {
    "SOFT": "softs", "S": "softs",
    "MEDIUM": "mediums", "M": "mediums",
    "HARD": "hards", "H": "hards",
    "INTERMEDIATE": "intermediates", "I": "intermediates",
    "WET": "wets", "W": "wets",
}
_COMPOUND_RU = {
    "SOFT": "софте", "S": "софте",
    "MEDIUM": "медиуме", "M": "медиуме",
    "HARD": "харде", "H": "харде",
    "INTERMEDIATE": "интермедиате", "I": "интермедиате",
    "WET": "дожде", "W": "дожде",
}

# Session status → display text
_STATUS_EN: dict[str, str] = {
    "red_flag": "Red flag — session stopped",
    "safety_car": "Safety car",
    "vsc": "VSC",
    "finished": "Chequered flag — race complete",
}
_STATUS_RU: dict[str, str] = {
    "red_flag": "Красный флаг — гонка остановлена",
    "safety_car": "Safety car",
    "vsc": "VSC",
    "finished": "Клетчатый флаг — финиш",
}


def _fmt_ms(ms: int) -> str:
    """Format milliseconds as m:ss.mmm."""
    total_s, ms_part = divmod(ms, 1000)
    minutes, secs = divmod(total_s, 60)
    return f"{minutes}:{secs:02d}.{ms_part:03d}"


def render_feed(
    events: list[Event],
    until_ms: int,
    lang: str = "en",
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return feed items from events up to until_ms, newest first."""

    # Work only with events up to until_ms
    visible = [e for e in events if e.session_time_ms <= until_ms]
    # Sort ascending for processing
    visible_sorted = sorted(visible, key=lambda e: (e.session_time_ms, e.event_id))

    # Pre-build index: driver_id -> sorted list of (session_time_ms, compound)
    # for TyreStintUpdated events, used for O(log n) PitOut↔tyre pairing.
    _stint_index: dict[str, list[tuple[int, str]]] = {}
    for _e in visible_sorted:
        if _e.type == "TyreStintUpdated" and _e.driver_id:
            compound_val = _e.payload.get("compound")
            if compound_val is not None:
                _stint_index.setdefault(_e.driver_id, []).append(
                    (_e.session_time_ms, compound_val)
                )
    # Lists are already in ascending order (visible_sorted is sorted)

    items: list[dict[str, Any]] = []

    # Track absolute fastest lap for fastest-lap feed items
    best_ms: int | None = None
    # Track previous session status to detect "Race resumed"
    prev_status: str | None = None
    # Track which status transitions already produced a feed item (avoid duplicates with RCM)
    emitted_status: set[str] = set()

    for e in visible_sorted:
        text: str | None = None
        driver_id: str | None = e.driver_id

        if e.type == "SessionStarted":
            if lang == "ru":
                text = "Свет погас — старт!"
            else:
                text = "Lights out — race start!"
            driver_id = None

        elif e.type == "LapCompleted":
            lap_ms = e.payload.get("lap_time_ms")
            if lap_ms is not None:
                if best_ms is None or lap_ms < best_ms:
                    best_ms = lap_ms
                    drv = e.driver_id or "?"
                    text = f"Fastest lap: {drv} {_fmt_ms(lap_ms)}"
                    driver_id = e.driver_id

        elif e.type == "PitIn":
            drv = e.driver_id or "?"
            if lang == "ru":
                text = f"{drv} заезжает в боксы"
            else:
                text = f"{drv} pits"
            driver_id = e.driver_id

        elif e.type == "PitOut":
            drv = e.driver_id or "?"
            # Look for TyreStintUpdated from the same driver within 5 s after PitOut
            # using pre-built index + bisect for O(log n) lookup.
            compound: str | None = None
            stints = _stint_index.get(e.driver_id or "", [])
            if stints:
                t0 = e.session_time_ms
                t1 = t0 + 5_000
                lo = bisect.bisect_left(stints, (t0,))
                if lo < len(stints) and stints[lo][0] <= t1:
                    compound = stints[lo][1]
            if compound:
                cname_en = _COMPOUND_EN.get(compound.upper(), compound.lower() + "s")
                cname_ru = _COMPOUND_RU.get(compound.upper(), compound.lower())
                if lang == "ru":
                    text = f"{drv} выезжает на {cname_ru}"
                else:
                    text = f"{drv} rejoins on {cname_en}"
            else:
                if lang == "ru":
                    text = f"{drv} выезжает из боксов"
                else:
                    text = f"{drv} rejoins"
            driver_id = e.driver_id

        elif e.type == "SessionStatusChanged":
            status = e.payload.get("status", "")
            if status == "started" and prev_status is not None and prev_status != "started":
                if lang == "ru":
                    text = "Гонка возобновлена"
                else:
                    text = "Race resumed"
                emitted_status.add(status)
            elif status in _STATUS_EN:
                text = _STATUS_RU.get(status, status) if lang == "ru" else _STATUS_EN[status]
                emitted_status.add(status)
            prev_status = status
            driver_id = None

        elif e.type == "RaceControlMessage":
            msg = e.payload.get("message", "")
            category = e.payload.get("category", "")
            msg_up = msg.upper()
            has_incident = "INCIDENT" in msg_up or "INVESTIGATION" in msg_up
            # For flag category, only include race-level flags (red flag, SC, VSC) —
            # exclude per-sector yellow/clear/green messages which are noise
            has_flag = (
                "Flag" in category
                and (
                    "RED FLAG" in msg_up
                    or "SAFETY CAR" in msg_up
                    or "VIRTUAL SAFETY CAR" in msg_up
                )
            )
            if not (has_flag or has_incident):
                continue
            # Avoid duplicating SessionStatusChanged items that already cover SC/VSC/red flag
            dup = False
            if "RED" in msg_up and "red_flag" in emitted_status:
                dup = True
            elif "SAFETY CAR" in msg_up and not "VIRTUAL" in msg_up and "safety_car" in emitted_status:
                dup = True
            elif "VIRTUAL" in msg_up and "vsc" in emitted_status:
                dup = True
            if dup:
                continue
            text = msg
            driver_id = None

        if text is None:
            continue

        # Determine tag for frontend chip
        if e.type in ("PitIn", "PitOut"):
            tag = "PIT"
        elif e.type in ("SessionStarted", "SessionStatusChanged", "RaceControlMessage"):
            tag = "FLAG"
        elif e.type == "LapCompleted":
            tag = "FASTEST"
        else:
            tag = "INFO"

        items.append({
            "at_ms": e.session_time_ms,
            "lap": e.lap,
            "kind": e.type,
            "tag": tag,
            "text": text,
            "driver_id": driver_id,
        })

    # Newest first, then apply limit
    items.sort(key=lambda x: x["at_ms"], reverse=True)
    return items[:limit]
