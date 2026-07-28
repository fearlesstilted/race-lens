"""Overtake / undercut detection from raw PositionChanged events.

detect_passes() works on the raw event list — NOT engine lap-checkpoint
sampling — so it is precise in time and works identically for replay
fixtures and the live event log.

Method: PositionChanged events are grouped into batches (gap ≤ _BATCH_GAP_MS);
comparing the position snapshot before/after a batch yields every pair whose
relative order inverted → X passed Y. Filters:
  * lap 1 skipped (start shuffle);
  * Y retired near the swap → not a pass;
  * X pitted out near the swap → rejoin, not a pass;
  * Y in the pits near the swap: if X pitted recently (fresh tyres jumped Y's
    pit cycle) → UNDERCUT; otherwise X merely inherited the place while Y
    pitted — churn, skipped (the feed already shows "Y pits").
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass

from racelens.events.models import Event

KIND_ON_TRACK = "ON_TRACK"
KIND_UNDERCUT = "UNDERCUT"

_BATCH_GAP_MS = 5_000    # position updates this close = one swap batch
_PIT_WINDOW_MS = 25_000  # pit in/out this close to a swap = pit-cycle move
_RETIRE_WINDOW_MS = 30_000
# ≥ this many cars passing the same driver within _SINK_WINDOW_MS = the driver
# is sinking (damage / crawling to the pits), not being raced — suppressed.
_SINK_COUNT = 3
_SINK_WINDOW_MS = 120_000
# An undercut requires X to have exited the pits shortly before jumping Y's stop:
# PitOut within ~2 laps before the swap. Time-based; lap-based if tracks vary.
_UNDERCUT_LOOKBACK_MS = 240_000


@dataclass(frozen=True)
class Pass:
    at_ms: int
    lap: int | None
    ahead: str      # driver who gained the place
    behind: str     # driver who lost it
    position: int   # ahead's new position
    kind: str       # KIND_ON_TRACK | KIND_UNDERCUT


def detect_passes(events: list[Event]) -> list[Pass]:
    pos_events = sorted(
        (e for e in events if e.type == "PositionChanged" and e.driver_id),
        key=lambda e: (e.session_time_ms, e.event_id),
    )
    if not pos_events:
        return []

    # Lap-1 cutoff and lap lookup from LapCompleted times.
    lap_marks = sorted(
        (e.session_time_ms, e.lap)
        for e in events
        if e.type == "LapCompleted" and e.lap is not None
    )
    lap1_end_ms = next((t for t, lap in lap_marks if lap == 1), None)

    def lap_at(t: int) -> int | None:
        if not lap_marks:
            return None
        i = bisect.bisect_right(lap_marks, (t, 999))
        return lap_marks[i - 1][1] + 1 if i else 1

    # Pit / retirement timelines for classification.
    pit_out: dict[str, list[int]] = {}
    pit_any: dict[str, list[int]] = {}
    retired: dict[str, int] = {}
    for e in events:
        if not e.driver_id:
            continue
        if e.type == "PitOut":
            pit_out.setdefault(e.driver_id, []).append(e.session_time_ms)
        if e.type in ("PitIn", "PitOut"):
            pit_any.setdefault(e.driver_id, []).append(e.session_time_ms)
        if e.type == "RetirementDetected":
            retired[e.driver_id] = e.session_time_ms

    def recent(times: list[int] | None, t: int, window: int) -> bool:
        if not times:
            return False
        i = bisect.bisect_left(times, t - window)
        return i < len(times) and times[i] <= t

    passes: list[Pass] = []
    pos: dict[str, int] = {}  # current snapshot (baseline = first batch, no passes)
    i = 0
    while i < len(pos_events):
        # Collect one batch.
        j = i + 1
        while (
            j < len(pos_events)
            and pos_events[j].session_time_ms - pos_events[j - 1].session_time_ms
            <= _BATCH_GAP_MS
        ):
            j += 1
        batch = pos_events[i:j]
        i = j

        before = dict(pos)
        for e in batch:
            pos[e.driver_id] = e.payload["position"]
        t = batch[-1].session_time_ms

        if not before or (lap1_end_ms is not None and t <= lap1_end_ms):
            continue  # grid baseline / lap-1 shuffle

        changed = {e.driver_id for e in batch}
        for x in changed:
            if x not in before:
                continue
            for y, y_before in before.items():
                if y == x or y not in pos:
                    continue
                if before[x] > y_before and pos[x] < pos[y]:  # order inverted: X now ahead
                    if recent(retired.get(y) and [retired[y]], t, _RETIRE_WINDOW_MS):
                        continue  # Y dropping out, not a pass
                    if recent(pit_out.get(x), t, _PIT_WINDOW_MS):
                        continue  # X rejoining traffic — position churn, not a pass
                    if recent(pit_any.get(y), t, _PIT_WINDOW_MS):
                        # Y is in its pit cycle. Undercut only if X's fresh
                        # tyres earned it; otherwise X just inherited the spot.
                        x_outs = pit_out.get(x)
                        if not x_outs or not any(
                            t - _UNDERCUT_LOOKBACK_MS <= to <= t for to in x_outs
                        ):
                            continue
                        kind = KIND_UNDERCUT
                    else:
                        kind = KIND_ON_TRACK
                    passes.append(
                        Pass(
                            at_ms=t, lap=lap_at(t), ahead=x, behind=y,
                            position=pos[x], kind=kind,
                        )
                    )

    # One batch can yield the same inversion from both sides' updates — dedup.
    seen: set[tuple[int, str, str]] = set()
    out = []
    for p in sorted(passes, key=lambda p: (p.at_ms, p.position)):
        key = (p.at_ms, p.ahead, p.behind)
        if key not in seen:
            seen.add(key)
            out.append(p)

    # Sinking filter: a wounded car being swallowed by the field is one story,
    # not fifteen "X passes Y" lines.
    by_behind: dict[str, list[int]] = {}
    for p in out:
        by_behind.setdefault(p.behind, []).append(p.at_ms)
    def sinking(p: Pass) -> bool:
        times = by_behind[p.behind]
        i = bisect.bisect_left(times, p.at_ms - _SINK_WINDOW_MS)
        j = bisect.bisect_right(times, p.at_ms)
        return j - i >= _SINK_COUNT
    return [p for p in out if not sinking(p)]
