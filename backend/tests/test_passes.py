"""detect_passes: swap detection, pit-cycle classification, noise filters."""
import json
from pathlib import Path

from racelens.events.models import Event, event
from racelens.insights.passes import KIND_ON_TRACK, KIND_UNDERCUT, detect_passes

SID = "test_race"
FIXTURE = Path(__file__).parent.parent / "fixtures" / "silverstone_2026_race.jsonl"


def _grid(*drivers: str) -> list[Event]:
    return [
        event(SID, "PositionChanged", 0, d, position=i + 1)
        for i, d in enumerate(drivers)
    ]


def test_on_track_undercut_and_filters() -> None:
    evs = _grid("A", "B", "C", "E", "F", "G", "H")
    evs.append(event(SID, "LapCompleted", 90_000, "A", lap=1, lap_time_ms=90_000))

    # Lap-1 shuffle (t <= lap-1 end) — must be skipped.
    evs.append(event(SID, "PositionChanged", 50_000, "B", position=1))
    evs.append(event(SID, "PositionChanged", 50_000, "A", position=2))
    # Undo it after lap 1 quietly?  No — keep B ahead; baseline continues.

    # On-track pass: A re-takes B at 200s.
    evs.append(event(SID, "PositionChanged", 200_000, "A", position=1))
    evs.append(event(SID, "PositionChanged", 200_000, "B", position=2))

    # Undercut: C pits early (out at 320s), A pits at 400s and comes out behind.
    evs.append(event(SID, "PitIn", 300_000, "C", lap=3))
    evs.append(event(SID, "PitOut", 320_000, "C", lap=4))
    evs.append(event(SID, "PitIn", 400_000, "A", lap=4))
    evs.append(event(SID, "PositionChanged", 410_000, "C", position=2))
    evs.append(event(SID, "PositionChanged", 410_000, "A", position=3))
    evs.append(event(SID, "PitOut", 425_000, "A", lap=5))

    # Rejoin churn: G exits the pits and the order jitters around it — skip.
    evs.append(event(SID, "PitIn", 500_000, "H", lap=5))
    evs.append(event(SID, "PitOut", 520_000, "H", lap=6))
    evs.append(event(SID, "PositionChanged", 530_000, "H", position=6))
    evs.append(event(SID, "PositionChanged", 530_000, "G", position=7))

    # Sinking: E swallowed by 3 cars in one batch — all suppressed.
    evs.append(event(SID, "PositionChanged", 700_000, "E", position=7))
    evs.append(event(SID, "PositionChanged", 700_000, "F", position=4))
    evs.append(event(SID, "PositionChanged", 700_000, "G", position=5))
    evs.append(event(SID, "PositionChanged", 700_000, "H", position=6))

    ps = detect_passes(evs)
    keys = {(p.ahead, p.behind, p.kind) for p in ps}

    assert ("A", "B", KIND_ON_TRACK) in keys          # plain pass detected
    assert ("C", "A", KIND_UNDERCUT) in keys          # pit-cycle jump classified
    assert not any(p.at_ms <= 90_000 for p in ps)     # lap-1 shuffle skipped
    assert not any(p.ahead == "H" for p in ps)        # rejoin churn skipped
    assert not any(p.behind == "E" for p in ps)       # sinking car suppressed
    on_track = next(p for p in ps if p.ahead == "A")
    assert on_track.position == 1 and on_track.lap == 2


def test_fixture_smoke() -> None:
    evs = [Event(**json.loads(ln)) for ln in FIXTURE.read_text().splitlines()]
    ps = detect_passes(evs)
    # Sanity band, not an exact golden: real race yields dozens, not hundreds.
    assert 30 <= len(ps) <= 90
    assert ("ANT", "HAM") in {(p.ahead, p.behind) for p in ps}  # known lap-11 pass
    assert all(p.kind in (KIND_ON_TRACK, KIND_UNDERCUT) for p in ps)
