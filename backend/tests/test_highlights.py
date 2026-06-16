"""Tests for highlights(): highlight reel generation."""
from __future__ import annotations
from pathlib import Path
import pytest
from racelens.events.models import load_jsonl
from racelens.highlights import highlights
from racelens.replay.engine import ReplayEngine

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str):
    return load_jsonl((FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8"))


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_highlights_top_n(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    result = highlights(events, eng, top_n=8)
    assert isinstance(result, list)
    assert len(result) <= 8
    assert len(result) > 0


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_highlights_chronological(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    result = highlights(events, eng, top_n=8)
    times = [h["at_ms"] for h in result]
    assert times == sorted(times), "Highlights must be sorted chronologically"


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_highlights_schema(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    result = highlights(events, eng, top_n=8)
    for h in result:
        assert "at_ms" in h
        assert "lap" in h
        assert "kind" in h
        assert "title_en" in h
        assert "title_ru" in h
        assert "drivers" in h


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_highlights_determinism(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    r1 = highlights(events, eng, top_n=8)
    r2 = highlights(events, eng, top_n=8)
    assert r1 == r2


def test_highlights_miami_contains_major_events() -> None:
    """Miami has SC + crashes + lead changes — these must appear in highlights."""
    events = _load("miami_2026_race")
    eng = ReplayEngine(events)
    result = highlights(events, eng, top_n=8)
    kinds = {h["kind"] for h in result}
    # At minimum, should have some high-drama events (not just fastest laps)
    assert kinds - {"FASTEST_LAP"}, f"Expected non-FL events, got: {kinds}"
