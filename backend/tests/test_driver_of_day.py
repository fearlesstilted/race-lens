"""Tests for driver_of_day(): algorithmic DOTD calculation."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
import pytest
from racelens.events.models import dump_jsonl, load_jsonl
from racelens.driver_of_day import (
    AwardNotFound,
    AwardValidationError,
    driver_of_day,
    load_official_award,
    parse_official_award,
    persist_official_award,
)
from racelens.replay.engine import ReplayEngine
from tests.test_object_storage import MemoryStore
from tests.test_replay import mini_race

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


def _official_html(*rows: dict) -> str:
    payload = json.dumps({"accordianData": [[row] for row in rows]}, separators=(",", ":"))
    push = json.dumps([1, f"prefix:{payload}:suffix"])
    return f"<html><script>self.__next_f.push({push})</script></html>"


def _official_row(**changes) -> dict:
    return {
        "votePosition": 1,
        "votePercentage": 30,
        "driverTLA": "VER",
        "meetingLocation": "Australia",
        **changes,
    }


def test_official_award_parses_exact_structured_match() -> None:
    fetched_at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    result = parse_official_award(
        _official_html(_official_row(), _official_row(meetingLocation="China", driverTLA="ANT")),
        year=2026,
        meeting="Australian Grand Prix",
        replay_id="australian_2026_race",
        replay_drivers={"VER", "NOR"},
        fetched_at=fetched_at,
    )
    assert result == {
        "schema_version": 1,
        "replay_id": "australian_2026_race",
        "meeting": "australia",
        "driver": "VER",
        "percentage": 30.0,
        "provider": "Formula 1 fan vote",
        "source_url": "https://www.formula1.com/en/results/2026/awards/driver-of-the-day",
        "fetched_at": "2026-08-10T12:00:00Z",
    }


@pytest.mark.parametrize(
    ("rows", "meeting", "error"),
    [
        ([_official_row()], "Japanese Grand Prix", AwardNotFound),
        ([_official_row(meetingLocation="Japan")], "Australian Grand Prix", AwardNotFound),
        ([_official_row(votePercentage=float("nan"))], "Australia", AwardValidationError),
        ([_official_row(driverTLA="Max")], "Australia", AwardValidationError),
        ([_official_row(), _official_row(driverTLA="NOR")], "Australia", AwardValidationError),
    ],
)
def test_official_award_fails_closed(rows, meeting, error) -> None:
    with pytest.raises(error):
        parse_official_award(
            _official_html(*rows),
            year=2026,
            meeting=meeting,
            replay_id="australian_2026_race",
            replay_drivers={"VER", "NOR"},
        )


def test_official_award_rejects_driver_missing_from_replay() -> None:
    with pytest.raises(AwardValidationError, match="replay"):
        parse_official_award(
            _official_html(_official_row()),
            year=2026,
            meeting="Australia",
            replay_id="australian_2026_race",
            replay_drivers={"NOR"},
        )


def test_official_award_local_first_then_object_storage(tmp_path) -> None:
    store = MemoryStore()
    record = parse_official_award(
        _official_html(_official_row()),
        year=2026,
        meeting="Australia",
        replay_id="australian_2026_race",
        replay_drivers={"VER"},
    )
    persist_official_award(record, tmp_path, store)
    assert load_official_award(tmp_path, store, "australian_2026_race", {"VER"}) == record

    local = tmp_path / "awards" / "driver-of-the-day" / "australian_2026_race.json"
    local.unlink()
    assert load_official_award(tmp_path, store, "australian_2026_race", {"VER"}) == record

    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("{}", encoding="utf-8")
    assert load_official_award(tmp_path, store, "australian_2026_race", {"VER"}) is None


def test_dotd_api_only_returns_official_result_after_finish(tmp_path, monkeypatch) -> None:
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import racelens.api as api

    assert fastapi
    replay_id = "mini_2026_race"
    events = mini_race()
    (tmp_path / f"{replay_id}.jsonl").write_text(dump_jsonl(events), encoding="utf-8")
    record = parse_official_award(
        _official_html(_official_row()),
        year=2026,
        meeting="Australia",
        replay_id=replay_id,
        replay_drivers={"VER", "NOR", "LEC"},
    )
    persist_official_award(record, tmp_path)
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine_cached.cache_clear()
    client = TestClient(api.app)

    provisional = client.get(
        f"/api/sessions/{replay_id}/driver-of-day", params={"at_ms": 100_000},
    )
    finished = client.get(f"/api/sessions/{replay_id}/driver-of-day")
    assert provisional.status_code == 200
    assert provisional.json()["official_result"] is None
    assert finished.status_code == 200
    assert finished.json()["official_result"] == {
        key: record[key]
        for key in ("driver", "percentage", "provider", "source_url", "fetched_at")
    }
