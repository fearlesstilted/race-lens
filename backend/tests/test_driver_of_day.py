"""Tests for driver_of_day(): algorithmic DOTD calculation."""
from __future__ import annotations
from pathlib import Path
import pytest
from racelens.events.models import load_jsonl
from racelens.driver_of_day import driver_of_day
from racelens.replay.engine import ReplayEngine

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str):
    return load_jsonl((FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8"))


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_driver_of_day_schema(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    result = driver_of_day(events, eng)
    assert "candidates" in result
    assert "computed_pick" in result
    assert isinstance(result["candidates"], list)
    assert len(result["candidates"]) > 0
    assert result["computed_pick"] is not None


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_driver_of_day_score_desc(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    result = driver_of_day(events, eng)
    scores = [c["score"] for c in result["candidates"]]
    assert scores == sorted(scores, reverse=True), "Candidates must be sorted score desc"


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_driver_of_day_determinism(session: str) -> None:
    events = _load(session)
    eng = ReplayEngine(events)
    r1 = driver_of_day(events, eng)
    r2 = driver_of_day(events, eng)
    assert r1 == r2


@pytest.mark.parametrize("session", ["spain_2024_race", "miami_2026_race"])
def test_driver_of_day_pick_sensible(session: str) -> None:
    """The computed pick should have gained at least some positions or have fastest lap."""
    events = _load(session)
    eng = ReplayEngine(events)
    result = driver_of_day(events, eng)
    top = result["candidates"][0]
    assert top["score"] > 0, f"Top candidate {top['driver']} has non-positive score {top['score']}"


def test_driver_of_day_candidate_fields() -> None:
    events = _load("spain_2024_race")
    eng = ReplayEngine(events)
    result = driver_of_day(events, eng)
    for c in result["candidates"]:
        assert "driver" in c
        assert "score" in c
        assert "positions_gained" in c
        assert "had_fastest_lap" in c
        assert "note_en" in c
        assert "note_ru" in c
