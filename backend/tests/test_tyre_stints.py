"""Tyre stint timeline tests."""
import os

import pytest

from racelens.events.models import event
from racelens.tyre_stints import stint_timeline

FIXTURES = os.environ.get("RACELENS_FIXTURES", "fixtures")


def _has_fixture(name: str) -> bool:
    import pathlib
    return (pathlib.Path(FIXTURES) / f"{name}.jsonl").exists()


SESSION = "miami_2026_race"


def test_tyre_only_driver_has_no_phantom_stint():
    events = [
        event("race", "TyreStintUpdated", 0, "DNS", compound="SOFT"),
        event("race", "TyreStintUpdated", 0, "RUN", compound="MEDIUM"),
        event("race", "LapCompleted", 90_000, "RUN", lap=1),
    ]

    assert stint_timeline(events, 70) == {
        "RUN": [{
            "compound": "MEDIUM",
            "start_lap": 1,
            "end_lap": 1,
            "laps": 1,
        }],
    }


@pytest.mark.skipif(not _has_fixture(SESSION), reason="fixture not available")
def test_stints_contiguous_and_bounded():
    from racelens.api import stints
    r = stints(SESSION)
    total = r["total_laps"]
    assert total > 0
    assert r["stints"], "no stints produced"

    for drv, rows in r["stints"].items():
        assert rows, f"{drv} has no stints"
        # First stint starts at lap 1.
        assert rows[0]["start_lap"] == 1, f"{drv} first stint not at lap 1"
        prev_end = 0
        for s in rows:
            # Contiguous, no gaps/overlaps between stints.
            assert s["start_lap"] == prev_end + 1, f"{drv} stint gap/overlap: {rows}"
            assert s["end_lap"] >= s["start_lap"]
            assert s["laps"] == s["end_lap"] - s["start_lap"] + 1
            prev_end = s["end_lap"]
        # Never runs past the race distance.
        assert prev_end <= total, f"{drv} stints exceed total laps"


@pytest.mark.skipif(not _has_fixture(SESSION), reason="fixture not available")
def test_stints_multistop_driver():
    from racelens.api import stints
    r = stints(SESSION)
    ver = r["stints"].get("VER")
    assert ver and len(ver) >= 2
    assert ver[0]["compound"] == "MEDIUM"
