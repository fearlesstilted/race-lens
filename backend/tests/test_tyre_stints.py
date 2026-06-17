"""Tyre stint timeline tests."""
import os

import pytest

FIXTURES = os.environ.get("RACELENS_FIXTURES", "fixtures")


def _has_fixture(name: str) -> bool:
    import pathlib
    return (pathlib.Path(FIXTURES) / f"{name}.jsonl").exists()


SESSION = "miami_2026_race"


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
