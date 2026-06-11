"""Tests for detect_battles and /battles endpoint (PLAN.md §15.4)."""
import pytest

from racelens.insights.battles import detect_battles
from racelens.replay.engine import ReplayEngine

from tests.test_replay import mini_race


# ── helpers ──────────────────────────────────────────────────────────────────

def _battle_state(**overrides):
    """Minimal state with one genuine battle pair."""
    state = {
        "at_ms": 300_000,
        "lap": 3,
        "session_status": "started",
        "classification": ["VER", "NOR"],
        "drivers": {
            "VER": {
                "interval_s": None,
                "in_pit": False,
                "last_lap_ms": 78_000,
            },
            "NOR": {
                "interval_s": 0.8,    # within battle threshold
                "in_pit": False,
                "last_lap_ms": 78_300,  # pace diff = 300ms < 600ms
            },
        },
    }
    state.update(overrides)
    return state


# ── unit tests ────────────────────────────────────────────────────────────────

def test_battle_detected():
    state = _battle_state()
    result = detect_battles(state)
    assert len(result) == 1
    ins = result[0]
    assert ins["type"] == "BATTLE_DETECTED"
    assert ins["severity"] == "medium"
    assert ins["driver_ids"] == ["VER", "NOR"]
    assert ins["evidence"]["interval_s"] == 0.8
    assert ins["evidence"]["positions"] == [1, 2]


def test_large_interval_no_battle():
    state = _battle_state()
    state["drivers"]["NOR"]["interval_s"] = 2.0
    assert detect_battles(state) == []


def test_large_pace_diff_no_battle():
    """Pace diff > 600ms means fast car is catching rapidly — traffic, not a battle."""
    state = _battle_state()
    state["drivers"]["NOR"]["last_lap_ms"] = 78_000 + 700  # diff = 700ms
    assert detect_battles(state) == []


def test_pit_driver_excluded():
    state = _battle_state()
    state["drivers"]["NOR"]["in_pit"] = True
    assert detect_battles(state) == []


def test_safety_car_returns_empty():
    state = _battle_state()
    state["session_status"] = "safety_car"
    assert detect_battles(state) == []


def test_finished_returns_empty():
    state = _battle_state()
    state["session_status"] = "finished"
    assert detect_battles(state) == []


def test_mini_race_at_247_no_battle():
    """LEC/NOR: interval=0.7 but pace diff=|79800-77000|=2800ms > 600ms → NOT a battle."""
    s = ReplayEngine(mini_race()).state_at(247_000)
    result = detect_battles(s)
    # LEC pace much faster than NOR — that's traffic risk, not a battle
    assert result == []


def test_synthetic_genuine_battle():
    """Two cars at 0.5s with 100ms pace difference → detected."""
    state = {
        "at_ms": 500_000,
        "lap": 5,
        "session_status": "started",
        "classification": ["HAM", "ALO"],
        "drivers": {
            "HAM": {
                "interval_s": None,
                "in_pit": False,
                "last_lap_ms": 82_000,
            },
            "ALO": {
                "interval_s": 0.5,
                "in_pit": False,
                "last_lap_ms": 82_100,
            },
        },
    }
    result = detect_battles(state)
    assert len(result) == 1
    assert result[0]["driver_ids"] == ["HAM", "ALO"]


# ── API endpoint test ─────────────────────────────────────────────────────────

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.events.models import dump_jsonl  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "2024_mini_race.jsonl").write_text(dump_jsonl(mini_race()), encoding="utf-8")
    import racelens.api as api

    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    api._engine.cache_clear()
    return TestClient(api.app)


def test_battles_endpoint_returns_empty_for_mini_race(client):
    """mini_race at 247s: LEC-NOR pace diff too large → battles list is empty."""
    r = client.get("/api/sessions/2024_mini_race/battles", params={"at_ms": 247_000})
    assert r.status_code == 200
    data = r.json()
    assert "at_ms" in data
    assert "battles" in data
    assert data["battles"] == []


def test_battles_endpoint_404(client):
    r = client.get("/api/sessions/nope/battles", params={"at_ms": 0})
    assert r.status_code == 404
