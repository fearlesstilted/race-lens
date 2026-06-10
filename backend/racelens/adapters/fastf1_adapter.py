"""FastF1 → normalized events.

Converts a loaded historical session into the Event timeline the replay
engine consumes. Telemetry is intentionally skipped in MVP — laps, positions,
stints and pits are enough for replay + strategy insights (PLAN.md §7.1).

Requires the `fastf1` extra:  pip install -e ".[fastf1]"
"""
from __future__ import annotations

from racelens.events.models import Event, event


def _ms(td) -> int | None:
    """pandas Timedelta → whole milliseconds, None for NaT."""
    import pandas as pd

    if td is None or pd.isna(td):
        return None
    return int(td.total_seconds() * 1000)


def _timestamp_to_session_ms(ts, session_zero) -> int | None:
    """Absolute timestamp → session-relative milliseconds."""
    import pandas as pd

    if ts is None or pd.isna(ts):
        return None
    return _ms(pd.Timestamp(ts) - session_zero)


def session_id_for(year: int, gp: str, session: str) -> str:
    return f"{year}_{gp.lower().replace(' ', '_')}_{session.lower()}"


def ingest_session(year: int, gp: str, session: str = "R") -> list[Event]:
    """Load a historical session via FastF1 and normalize it to events.

    First call downloads data into the FastF1 cache (slow, ~tens of MB);
    subsequent calls are local.
    """
    import fastf1
    import pandas as pd

    ses = fastf1.get_session(year, gp, session)
    ses.load(telemetry=False, weather=False, messages=True)

    sid = session_id_for(year, gp, session)
    src = "fastf1"
    events: list[Event] = []

    total_laps = getattr(ses, "total_laps", None)
    events.append(
        event(sid, "SessionStarted", 0, source=src,
              total_laps=int(total_laps) if total_laps else None)
    )

    by_lap: dict[int, list[tuple[int, int, str]]] = {}  # lap → [(position, t_end, driver)]
    for _, lap in ses.laps.iterlaps():
        drv = str(lap["Driver"])
        lap_no = int(lap["LapNumber"])
        t_end = _ms(lap["Time"])  # session time when the lap was completed
        if t_end is None:
            continue

        events.append(
            event(sid, "LapCompleted", t_end, drv, lap=lap_no, source=src,
                  lap_time_ms=_ms(lap["LapTime"]))
        )
        if not pd.isna(lap["Position"]):
            pos = int(lap["Position"])
            events.append(
                event(sid, "PositionChanged", t_end, drv, lap=lap_no, source=src,
                      position=pos)
            )
            by_lap.setdefault(lap_no, []).append((pos, t_end, drv))

    # Timing-screen gaps/intervals, derived from line-crossing times on the
    # same lap number. Approximation: exact for cars on the lead lap, coarse
    # for lapped cars — good enough for MVP strategy insights.
    for lap_no, rows in by_lap.items():
        rows.sort()
        leader_t = rows[0][1]
        prev_t = leader_t
        for pos, t, drv in rows:
            if pos > 1:
                events.append(event(sid, "GapUpdated", t, drv, lap=lap_no, source=src,
                                    gap_s=round((t - leader_t) / 1000, 3)))
                events.append(event(sid, "IntervalUpdated", t, drv, lap=lap_no, source=src,
                                    interval_s=round((t - prev_t) / 1000, 3)))
            prev_t = t

        t_pit_in = _ms(lap["PitInTime"])
        if t_pit_in is not None:
            events.append(event(sid, "PitIn", t_pit_in, drv, lap=lap_no, source=src))
        t_pit_out = _ms(lap["PitOutTime"])
        if t_pit_out is not None:
            events.append(event(sid, "PitOut", t_pit_out, drv, lap=lap_no, source=src))
            if not pd.isna(lap["Compound"]):
                events.append(
                    event(sid, "TyreStintUpdated", t_pit_out, drv, lap=lap_no, source=src,
                          compound=str(lap["Compound"]),
                          age_laps=int(lap["TyreLife"]) if not pd.isna(lap["TyreLife"]) else 0)
                )

    # Starting tyres: first stint per driver has no preceding PitOut
    for drv in ses.laps["Driver"].unique():
        first = ses.laps.pick_drivers(drv).iloc[0]
        if not pd.isna(first["Compound"]):
            events.append(
                event(sid, "TyreStintUpdated", 0, str(drv), source=src,
                      compound=str(first["Compound"]),
                      age_laps=int(first["TyreLife"]) - 1 if not pd.isna(first["TyreLife"]) else 0)
            )

    # Starting grid at t=0, so the timing table is populated before lap 1
    if ses.results is not None:
        for _, row in ses.results.iterrows():
            if not pd.isna(row.get("GridPosition")) and row["GridPosition"] > 0:
                events.append(
                    event(sid, "PositionChanged", 0, str(row["Abbreviation"]), source=src,
                          position=int(row["GridPosition"]))
                )

    # Race control messages ride along; flag messages also become session
    # status changes so the UI can show RED FLAG / SC / VSC instead of silence
    _STATUS = (
        ("RED FLAG", "red_flag"),
        ("VIRTUAL SAFETY CAR DEPLOYED", "vsc"),
        ("SAFETY CAR DEPLOYED", "safety_car"),
        ("GREEN LIGHT", "started"),
        ("TRACK CLEAR", "started"),
        ("CHEQUERED FLAG", "finished"),
    )
    if ses.race_control_messages is not None:
        session_zero = pd.Timestamp(ses.date) - pd.Timedelta(ses.session_start_time)
        for _, msg in ses.race_control_messages.iterrows():
            t = _timestamp_to_session_ms(msg.get("Time"), session_zero) if "Time" in msg else None
            if t is None or t < 0:
                continue
            text = str(msg.get("Message", ""))
            events.append(
                event(sid, "RaceControlMessage", t, source=src,
                      category=str(msg.get("Category", "")), message=text)
            )
            for needle, status in _STATUS:
                if needle in text:
                    events.append(
                        event(sid, "SessionStatusChanged", t, source=src, status=status)
                    )
                    break

    # Rebase to race start: FastF1 session time begins with the data feed,
    # ~1.5h before lights out. t0 = earliest lap-1 start (Time - LapTime).
    lap1 = ses.laps[ses.laps["LapNumber"] == 1]
    starts = (lap1["Time"] - lap1["LapTime"]).dropna()
    t0_ms = _ms(starts.min()) if len(starts) else 0
    if t0_ms:
        for e in events:
            e.session_time_ms = max(e.session_time_ms - t0_ms, 0)

    events.sort(key=lambda e: (e.session_time_ms, e.event_id))
    return events
