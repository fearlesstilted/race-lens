"""Tests for mini-sector gap events derived from FastF1 RelativeDistance telemetry."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import racelens.positions.mini_sectors as mini_sectors
import racelens.recorder.postprocess as postprocess
from racelens.cli import _cmd_mini_sectors
from racelens.events.models import dump_jsonl, event, load_jsonl

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


def test_mini_sector_replacement_is_validated_source_scoped_and_atomic(
    tmp_path, monkeypatch,
):
    session_id = "test_race"
    fixture = tmp_path / f"{session_id}.jsonl"
    unrelated = event(
        session_id, "GapUpdated", 1000, "VER", source="fastf1", gap_s=0.0,
    )
    old = [
        event(session_id, "GapUpdated", 2000, "NOR", source="mini_sectors", gap_s=1.0),
        event(
            session_id, "IntervalUpdated", 2000, "NOR",
            source="mini_sectors", interval_s=1.0,
        ),
    ]
    fixture.write_text(dump_jsonl([unrelated, *old]), encoding="utf-8")
    original = fixture.read_bytes()
    args = SimpleNamespace(
        year=2026, gp="Test", session="R", session_id=session_id,
    )
    monkeypatch.setenv("RACELENS_FIXTURES", str(tmp_path))

    monkeypatch.setattr(mini_sectors, "compute_gap_events", lambda *_: [])
    with pytest.raises(SystemExit, match="invalid empty"):
        _cmd_mini_sectors(args)
    assert fixture.read_bytes() == original

    replacement = [
        event(
            session_id, "GapUpdated", 3000, "NOR",
            source="mini_sectors", gap_s=0.5,
        ),
        event(
            session_id, "IntervalUpdated", 3000, "NOR",
            source="mini_sectors", interval_s=0.5,
        ),
    ]
    monkeypatch.setattr(mini_sectors, "compute_gap_events", lambda *_: replacement)
    real_replace = postprocess.os.replace

    def fail_replace(*_):
        raise OSError("interrupted")

    monkeypatch.setattr(postprocess.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        _cmd_mini_sectors(args)
    assert fixture.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))

    monkeypatch.setattr(postprocess.os, "replace", real_replace)
    _cmd_mini_sectors(args)
    written = load_jsonl(fixture.read_text(encoding="utf-8"))
    old_ids = {event_.event_id for event_ in old}
    assert unrelated in written
    assert not any(item.event_id in old_ids for item in written)
    assert all(item in written for item in replacement)
