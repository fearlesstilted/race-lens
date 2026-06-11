"""Tests for the tyre degradation trend insight detector and its commentary."""
from racelens.commentary.renderer import render
from racelens.insights.degradation import detect_degradation
from racelens.replay.engine import ReplayEngine

from tests.test_replay import mini_race


# ── Detector tests ─────────────────────────────────────────────────────────────

def _state(recent_laps_ms, tyre_age_laps, in_pit=False, at_ms=500_000):
    """Minimal state dict for detector unit tests."""
    return {
        "at_ms": at_ms,
        "lap": 10,
        "drivers": {
            "TST": {
                "recent_laps_ms": recent_laps_ms,
                "tyre_age_laps": tyre_age_laps,
                "in_pit": in_pit,
            }
        },
    }


def test_degradation_detected():
    # 3 monotonically growing laps, drift = 500 ms, age >= 5
    s = _state([80_000, 80_200, 80_500], tyre_age_laps=10)
    found = detect_degradation(s)
    assert len(found) == 1
    ins = found[0]
    assert ins["type"] == "DEGRADATION_TREND_DETECTED"
    assert ins["severity"] == "medium"  # 500 < 1000
    assert ins["driver_ids"] == ["TST"]
    assert ins["evidence"]["drift_ms"] == 500
    assert ins["evidence"]["tyre_age_laps"] == 10


def test_degradation_high_severity():
    s = _state([80_000, 80_500, 81_200], tyre_age_laps=12)
    found = detect_degradation(s)
    assert len(found) == 1
    assert found[0]["severity"] == "high"  # drift = 1200 >= 1000


def test_no_degradation_plateau():
    # Last lap same as middle lap — not strictly increasing
    s = _state([80_000, 80_300, 80_300], tyre_age_laps=10)
    assert detect_degradation(s) == []


def test_no_degradation_drift_too_small():
    # Only 300 ms drift — below threshold
    s = _state([80_000, 80_100, 80_300], tyre_age_laps=10)
    assert detect_degradation(s) == []


def test_no_degradation_fresh_tyres():
    # Tyre age < 5 laps
    s = _state([80_000, 80_200, 80_500], tyre_age_laps=3)
    assert detect_degradation(s) == []


def test_no_degradation_in_pit():
    s = _state([80_000, 80_200, 80_500], tyre_age_laps=10, in_pit=True)
    assert detect_degradation(s) == []


def test_no_degradation_too_few_laps():
    s = _state([80_000, 80_500], tyre_age_laps=10)
    assert detect_degradation(s) == []


def test_no_degradation_mini_race_fresh_tyres():
    """In mini_race LEC runs only 3 laps and tyre_age never hits 5 — no insight."""
    engine = ReplayEngine(mini_race())
    state = engine.state_at(300_000)
    found = detect_degradation(state)
    assert found == []


# ── Renderer tests ─────────────────────────────────────────────────────────────

DEGR = {
    "insight_id": "degradation:TST:1",
    "type": "DEGRADATION_TREND_DETECTED",
    "severity": "medium",
    "lap": 20,
    "driver_ids": ["TST"],
    "evidence": {"laps_ms": [80_000, 80_300, 80_700], "drift_ms": 700, "tyre_age_laps": 15},
}


def test_render_en_pro():
    text = render(DEGR, "en", "pro")
    assert "TST" in text
    assert "0.7s" in text
    assert "15" in text


def test_render_en_beginner():
    text = render(DEGR, "en", "beginner")
    assert "TST" in text
    assert "tyres" in text.lower()


def test_render_ru_pro():
    text = render(DEGR, "ru", "pro")
    assert "TST" in text
    assert "0.7с" in text or "0.7" in text


def test_render_ru_beginner():
    text = render(DEGR, "ru", "beginner")
    assert "TST" in text
    assert "боксы" in text or "резина" in text
