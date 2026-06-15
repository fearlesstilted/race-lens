"""Tests for the SC pit window insight detector and its renderer templates."""
from __future__ import annotations

import pytest

from racelens.insights.sc_pit import detect_sc_pit, MIN_TYRE_AGE_LAPS
from racelens.commentary.renderer import render


def _state(
    session_status: str = "safety_car",
    tyre_age_laps: int = 15,
    in_pit: bool = False,
) -> dict:
    return {
        "at_ms": 800_000,
        "lap": 20,
        "session_status": session_status,
        "classification": ["VER"],
        "drivers": {
            "VER": {
                "position": 1,
                "in_pit": in_pit,
                "tyre_age_laps": tyre_age_laps,
                "gap_s": None,
            }
        },
    }


# ── Detector ──────────────────────────────────────────────────────────────────

def test_sc_pit_fires_under_safety_car_with_old_tyres():
    insights = detect_sc_pit(_state(session_status="safety_car", tyre_age_laps=15))
    assert len(insights) == 1
    ins = insights[0]
    assert ins["type"] == "SC_PIT_WINDOW"
    assert ins["severity"] == "high"
    assert ins["driver_ids"] == ["VER"]
    assert ins["evidence"]["tyre_age_laps"] == 15


def test_sc_pit_no_insight_under_green_flag():
    insights = detect_sc_pit(_state(session_status="started"))
    assert insights == []


def test_sc_pit_no_insight_under_vsc():
    insights = detect_sc_pit(_state(session_status="vsc"))
    assert insights == []


def test_sc_pit_no_insight_with_fresh_tyres():
    """Tyres younger than MIN_TYRE_AGE_LAPS should not trigger the insight."""
    insights = detect_sc_pit(_state(tyre_age_laps=MIN_TYRE_AGE_LAPS - 1))
    assert insights == []


def test_sc_pit_no_insight_when_in_pit():
    insights = detect_sc_pit(_state(in_pit=True))
    assert insights == []


def test_sc_pit_no_insight_when_tyre_age_none():
    state = _state()
    state["drivers"]["VER"]["tyre_age_laps"] = None
    insights = detect_sc_pit(state)
    assert insights == []


def test_sc_pit_fires_at_boundary_age():
    """Exactly MIN_TYRE_AGE_LAPS should trigger."""
    insights = detect_sc_pit(_state(tyre_age_laps=MIN_TYRE_AGE_LAPS))
    assert len(insights) == 1


def test_sc_pit_multiple_drivers():
    state = {
        "at_ms": 900_000,
        "lap": 22,
        "session_status": "safety_car",
        "classification": ["VER", "HAM", "LEC"],
        "drivers": {
            "VER": {"position": 1, "in_pit": False, "tyre_age_laps": 20, "gap_s": None},
            "HAM": {"position": 2, "in_pit": True,  "tyre_age_laps": 18, "gap_s": 5.0},
            "LEC": {"position": 3, "in_pit": False, "tyre_age_laps": 3,  "gap_s": 8.0},
        },
    }
    insights = detect_sc_pit(state)
    # HAM in pit, LEC fresh tyres — only VER qualifies
    assert len(insights) == 1
    assert insights[0]["driver_ids"] == ["VER"]


# ── Renderer ──────────────────────────────────────────────────────────────────

def _make_insight(age: int = 15) -> dict:
    return {
        "type": "SC_PIT_WINDOW",
        "severity": "high",
        "driver_ids": ["VER"],
        "evidence": {"tyre_age_laps": age, "position": 1},
    }


def test_render_sc_pit_en_pro():
    text = render(_make_insight(), lang="en", level="pro")
    assert "VER" in text
    assert "Safety Car" in text
    assert "15" in text


def test_render_sc_pit_en_beginner():
    text = render(_make_insight(), lang="en", level="beginner")
    assert "VER" in text
    assert "15" in text


def test_render_sc_pit_ru_pro():
    text = render(_make_insight(), lang="ru", level="pro")
    assert "VER" in text
    assert "безопасности" in text
    assert "15" in text


def test_render_sc_pit_ru_beginner():
    text = render(_make_insight(), lang="ru", level="beginner")
    assert "VER" in text
    assert "15" in text
