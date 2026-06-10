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
            events.append(
                event(sid, "PositionChanged", t_end, drv, lap=lap_no, source=src,
                      position=int(lap["Position"]))
            )

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

    # Race control messages ride along for the future insight engine
    if ses.race_control_messages is not None:
        for _, msg in ses.race_control_messages.iterrows():
            t = _ms(msg.get("Time") - ses.session_start_time) if "Time" in msg else None
            if t is None or t < 0:
                continue
            events.append(
                event(sid, "RaceControlMessage", t, source=src,
                      category=str(msg.get("Category", "")),
                      message=str(msg.get("Message", "")))
            )

    events.sort(key=lambda e: (e.session_time_ms, e.event_id))
    return events
