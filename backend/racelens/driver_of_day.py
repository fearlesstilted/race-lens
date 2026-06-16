"""Driver of the Day: deterministic algorithmic pick based on race performance."""
from __future__ import annotations
from typing import Any
from racelens.events.models import Event
from racelens.replay.engine import ReplayEngine

# Scoring weights (document them here):
# positions_gained: 3.0 pts per position gained from start to finish
# had_fastest_lap: flat 15 pts bonus
# recovery_bonus: extra 10 pts if gained >= 5 positions (comeback bonus)
# pit_efficiency: -0.5 pts per extra pit stop above 1 (penalise stop-go strategies slightly)

W_POSITIONS_GAINED = 3.0
W_FASTEST_LAP = 15.0
W_RECOVERY = 10.0  # bonus for 5+ positions gained
W_PIT_EXTRA = -0.5  # per pit beyond 1


def driver_of_day(
    events: list[Event],
    state_engine: ReplayEngine,
) -> dict[str, Any]:
    """Compute Driver of the Day candidates.

    Returns:
        {
          candidates: [
            {driver, score, positions_gained, had_fastest_lap, note_en, note_ru},
            ... top 5 desc by score
          ],
          computed_pick: driver_id  # candidate[0].driver
        }
    """
    # Get starting grid: earliest PositionChanged for each driver
    start_positions: dict[str, int] = {}
    for e in sorted(events, key=lambda x: (x.session_time_ms, x.event_id)):
        if e.type == "PositionChanged" and e.driver_id not in start_positions:
            pos = e.payload.get("position")
            if pos is not None:
                start_positions[e.driver_id] = pos

    # Final state
    final_ms = max(e.session_time_ms for e in events)
    final_state = state_engine.state_at(final_ms)
    drivers_state = final_state["drivers"]

    # Find absolute fastest lap in the race
    best_lap_ms: int | None = None
    for ds in drivers_state.values():
        bl = ds.get("best_lap_ms")
        if bl is not None and (best_lap_ms is None or bl < best_lap_ms):
            best_lap_ms = bl
    fastest_lap_holder: str | None = None
    if best_lap_ms is not None:
        for drv, ds in drivers_state.items():
            if ds.get("best_lap_ms") == best_lap_ms:
                fastest_lap_holder = drv
                break

    candidates = []
    for drv, ds in drivers_state.items():
        if ds.get("retired"):
            continue
        if ds.get("position") is None:
            continue

        start_pos = start_positions.get(drv)
        final_pos = ds.get("position")
        if start_pos is None or final_pos is None:
            continue

        positions_gained = start_pos - final_pos  # positive = moved forward
        had_fastest_lap = (drv == fastest_lap_holder)
        extra_pits = max(0, ds.get("pit_count", 1) - 1)

        score = (
            positions_gained * W_POSITIONS_GAINED
            + (W_FASTEST_LAP if had_fastest_lap else 0.0)
            + (W_RECOVERY if positions_gained >= 5 else 0.0)
            + extra_pits * W_PIT_EXTRA
        )

        # Human-readable note
        if positions_gained > 0:
            note_en = f"Gained {positions_gained} position{'s' if positions_gained != 1 else ''} (P{start_pos}→P{final_pos})"
            note_ru = f"Отыграл {positions_gained} позиц. (P{start_pos}→P{final_pos})"
        elif positions_gained == 0:
            note_en = f"Held P{final_pos}"
            note_ru = f"Удержал P{final_pos}"
        else:
            note_en = f"Lost {-positions_gained} positions (P{start_pos}→P{final_pos})"
            note_ru = f"Потерял {-positions_gained} позиц. (P{start_pos}→P{final_pos})"

        if had_fastest_lap:
            note_en += " + fastest lap"
            note_ru += " + быстрейший круг"

        candidates.append({
            "driver": drv,
            "score": round(score, 2),
            "positions_gained": positions_gained,
            "had_fastest_lap": had_fastest_lap,
            "note_en": note_en,
            "note_ru": note_ru,
        })

    # Sort by score desc, then driver code for determinism
    candidates.sort(key=lambda c: (-c["score"], c["driver"]))

    top5 = candidates[:5]
    computed_pick = top5[0]["driver"] if top5 else None

    return {
        "candidates": top5,
        "computed_pick": computed_pick,
    }
