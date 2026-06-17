"""Tests for mini-sector gap events derived from FastF1 RelativeDistance telemetry."""
import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(os.environ.get("RACELENS_FIXTURES", Path(__file__).parent.parent / "fixtures"))


def load_fixture(session_id: str):
    from racelens.events.models import load_jsonl

    path = FIXTURES_DIR / f"{session_id}.jsonl"
    if not path.exists():
        pytest.skip(f"fixture {path} not found")
    return load_jsonl(path.read_text(encoding="utf-8"))


def test_mini_sector_gap_count_exceeds_per_lap(session_id="miami_2026_race"):
    """After mini-sectors ingest, a driver must have many more gap events than laps."""
    events = load_fixture(session_id)
    gap_events = [e for e in events if e.type == "GapUpdated" and e.source == "mini_sectors"]
    assert len(gap_events) > 0, "No mini-sector GapUpdated events found"

    # Group by driver
    from collections import defaultdict

    by_driver = defaultdict(list)
    for e in gap_events:
        if e.driver_id:
            by_driver[e.driver_id].append(e)

    assert by_driver, "No driver gap events found"

    # At least one driver must have >= 15 gap events on a single lap
    # (K=20 gates, so a driver behind the leader gets up to 20 per lap)
    from collections import Counter

    found = False
    for drv, evts in by_driver.items():
        lap_counts = Counter(e.lap for e in evts)
        if max(lap_counts.values()) >= 15:
            found = True
            break
    assert found, "No driver has >= 15 mini-sector gap events on a single lap"


def test_mini_sector_gaps_non_negative(session_id="miami_2026_race"):
    """All gap_s values must be non-negative."""
    events = load_fixture(session_id)
    bad = [
        e for e in events
        if e.type == "GapUpdated" and e.source == "mini_sectors"
        and e.payload.get("gap_s", 0) < 0
    ]
    assert not bad, f"Found {len(bad)} negative gap_s events"
