"""Tests for the OpenF1 adapter — no network, all HTTP mocked."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest

import racelens.adapters.openf1_adapter as _mod
from racelens.replay.engine import ReplayEngine

# ── Canned fixtures ──────────────────────────────────────────────────────────

_SESSION_KEY = 9999

_SESSIONS = [
    {
        "session_key": _SESSION_KEY,
        "session_name": "Race",
        "year": 2024,
        "location": "Monaco",
        "country_name": "Monaco",
        "circuit_short_name": "Monaco",
    }
]

_DRIVERS = [
    {"driver_number": 1, "name_acronym": "VER"},
    {"driver_number": 16, "name_acronym": "LEC"},
    {"driver_number": 4, "name_acronym": "NOR"},
]

# Three drivers, 2 laps each.
# Lap 1 starts at a common anchor.  VER is fastest each lap.
_T0 = "2024-05-26T13:00:00.000"  # session zero for rebase (lap 1 start)
_LAPS = [
    # VER lap 1: starts at T0, duration 78s
    {"driver_number": 1, "lap_number": 1, "date_start": _T0, "lap_duration": 78.0},
    # LEC lap 1: same start, 79s
    {"driver_number": 16, "lap_number": 1, "date_start": _T0, "lap_duration": 79.0},
    # NOR lap 1: same start, 80s
    {"driver_number": 4, "lap_number": 1, "date_start": _T0, "lap_duration": 80.0},
    # VER lap 2: starts after lap 1, 78s
    {"driver_number": 1, "lap_number": 2, "date_start": "2024-05-26T13:01:18.000", "lap_duration": 78.0},
    # LEC lap 2
    {"driver_number": 16, "lap_number": 2, "date_start": "2024-05-26T13:01:19.000", "lap_duration": 79.0},
    # NOR lap 2
    {"driver_number": 4, "lap_number": 2, "date_start": "2024-05-26T13:01:20.000", "lap_duration": 80.0},
]

_POSITIONS = [
    {"driver_number": 1, "position": 1, "date": _T0},
    {"driver_number": 16, "position": 2, "date": _T0},
    {"driver_number": 4, "position": 3, "date": _T0},
    # NOR overtakes LEC at lap 1 end
    {"driver_number": 4, "position": 2, "date": "2024-05-26T13:01:19.500"},
    {"driver_number": 16, "position": 3, "date": "2024-05-26T13:01:19.500"},
]

_PITS = [
    # LEC pits at lap 1, pit_duration 25s
    {"driver_number": 16, "lap_number": 1, "pit_duration": 25.0, "date": "2024-05-26T13:01:10.000"},
]

_STINTS = [
    {"driver_number": 1, "lap_start": 1, "lap_end": 2, "compound": "MEDIUM", "tyre_age_at_start": 0},
    {"driver_number": 16, "lap_start": 1, "lap_end": 1, "compound": "SOFT", "tyre_age_at_start": 0},
    {"driver_number": 16, "lap_start": 2, "lap_end": 2, "compound": "HARD", "tyre_age_at_start": 0},
    {"driver_number": 4, "lap_start": 1, "lap_end": 2, "compound": "MEDIUM", "tyre_age_at_start": 0},
]

_INTERVALS = [
    # dense stream — 30 entries per driver at 3-second intervals → only 2 should
    # survive per driver (sampled ≤ 1 per 30 s)
    *(
        {
            "driver_number": 16,
            "date": f"2024-05-26T13:01:{i:02d}.000",
            "gap_to_leader": round(1.0 + i * 0.05, 3),
            "interval": round(0.5 + i * 0.02, 3),
        }
        for i in range(0, 90, 3)
    ),
    *(
        {
            "driver_number": 4,
            "date": f"2024-05-26T13:01:{i:02d}.000",
            "gap_to_leader": round(2.0 + i * 0.05, 3),
            "interval": round(1.0 + i * 0.02, 3),
        }
        for i in range(0, 90, 3)
    ),
]

_RACE_CONTROL = [
    {"date": "2024-05-26T13:00:00.500", "category": "Flag", "message": "GREEN LIGHT - PIT EXIT OPEN", "flag": "GREEN"},
    {"date": "2024-05-26T13:02:40.000", "category": "Flag", "message": "CHEQUERED FLAG", "flag": "CHEQUERED"},
]


def _make_mock_get(overrides: dict | None = None):
    """Return a mock _get function that serves canned data based on path."""
    data = {
        "/sessions": _SESSIONS,
        "/drivers": _DRIVERS,
        "/laps": _LAPS,
        "/position": _POSITIONS,
        "/pit": _PITS,
        "/stints": _STINTS,
        "/intervals": _INTERVALS,
        "/race_control": _RACE_CONTROL,
    }
    if overrides:
        data.update(overrides)

    def _get(path, params=None):
        return list(data.get(path, []))

    return _get


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ingest(overrides=None):
    with patch.object(_mod, "_get", _make_mock_get(overrides)):
        return _mod.ingest_openf1(_SESSION_KEY)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_event_types_present():
    events = _ingest()
    types = {e.type for e in events}
    assert "SessionStarted" in types
    assert "LapCompleted" in types
    assert "PositionChanged" in types
    assert "PitIn" in types
    assert "PitOut" in types
    assert "TyreStintUpdated" in types
    assert "GapUpdated" in types
    assert "IntervalUpdated" in types
    assert "RaceControlMessage" in types
    assert "SessionStatusChanged" in types


def test_lap1_start_rebased_to_zero():
    """Earliest lap-1 date_start should map to session_time_ms=0."""
    events = _ingest()
    # The SessionStarted event is always at t=0; also, the first LapCompleted
    # for lap 1 should have session_time_ms == lap_duration_ms (78_000 for VER).
    lap_completions = [e for e in events if e.type == "LapCompleted" and e.lap == 1]
    assert lap_completions, "Expected LapCompleted events for lap 1"
    ver_lap1 = next(e for e in lap_completions if e.driver_id == "VER")
    assert ver_lap1.session_time_ms == 78_000
    assert ver_lap1.payload.get("lap_time_ms") == 78_000


def test_interval_sampling():
    """Intervals should be sampled to at most 1 per driver per 30 s."""
    events = _ingest()
    intervals = [e for e in events if e.type == "GapUpdated"]
    lec_intervals = [e for e in intervals if e.driver_id == "LEC"]
    nor_intervals = [e for e in intervals if e.driver_id == "NOR"]

    # 90 seconds of data at 3-second intervals → floor(90/30) = 3 samples
    # (at t=0s, t=30s, t=60s of the interval window; actual counts may vary by 1)
    assert len(lec_intervals) <= 4, f"Too many LEC intervals: {len(lec_intervals)}"
    assert len(nor_intervals) <= 4, f"Too many NOR intervals: {len(nor_intervals)}"


def test_ingest_seq_monotonic():
    """ingest_seq reflects arrival (creation) order — values are unique and span 0..n-1.

    After ingest, events are sorted by session_time_ms so the seq values will
    NOT appear in sorted order in the final list — that is expected.
    """
    events = _ingest()
    seqs = [e.ingest_seq for e in events if e.ingest_seq is not None]
    assert len(seqs) == len(events), "All events must have ingest_seq set"
    assert sorted(seqs) == list(range(len(seqs))), (
        "ingest_seq should be unique consecutive integers 0..n-1"
    )


def test_source_tag():
    events = _ingest()
    for e in events:
        assert e.source == "openf1", f"Unexpected source on {e}"


def test_dedup_via_replay_engine():
    """Ingesting twice and feeding all events to ReplayEngine → 0 duplicates."""
    first = _ingest()
    second = _ingest()
    engine = ReplayEngine(first + second)
    # All second-run events are exact duplicates of first-run events (same deterministic IDs)
    assert engine.duplicates_dropped == len(first)


def test_pit_events():
    events = _ingest()
    pit_ins = [e for e in events if e.type == "PitIn" and e.driver_id == "LEC"]
    pit_outs = [e for e in events if e.type == "PitOut" and e.driver_id == "LEC"]
    assert len(pit_ins) == 1
    assert len(pit_outs) == 1
    # PitOut must be after PitIn
    assert pit_outs[0].session_time_ms > pit_ins[0].session_time_ms


def test_position_changed_dedup():
    """PositionChanged should only be emitted on actual position changes."""
    events = _ingest()
    # VER stays P1 throughout; there should be only 1 PositionChanged for VER
    ver_pos = [e for e in events if e.type == "PositionChanged" and e.driver_id == "VER"]
    assert len(ver_pos) == 1


def test_tyre_stints():
    events = _ingest()
    stint_evts = [e for e in events if e.type == "TyreStintUpdated"]
    drivers_with_stints = {e.driver_id for e in stint_evts}
    assert "VER" in drivers_with_stints
    assert "LEC" in drivers_with_stints

    # LEC has 2 stints (SOFT → HARD)
    lec_stints = [e for e in stint_evts if e.driver_id == "LEC"]
    compounds = [e.payload["compound"] for e in lec_stints]
    assert "SOFT" in compounds
    assert "HARD" in compounds


def test_session_status_from_race_control():
    events = _ingest()
    statuses = [e for e in events if e.type == "SessionStatusChanged"]
    status_values = [e.payload["status"] for e in statuses]
    assert "started" in status_values
    assert "finished" in status_values


def test_empty_endpoints_dont_crash():
    """If all endpoints return empty, ingest should return only SessionStarted."""
    empty: dict = {
        "/drivers": [],
        "/laps": [],
        "/position": [],
        "/pit": [],
        "/stints": [],
        "/intervals": [],
        "/race_control": [],
    }
    events = _ingest(overrides=empty)
    assert len(events) == 1
    assert events[0].type == "SessionStarted"


def test_find_session_mock():
    """find_session resolves case-insensitively by country_name substring."""
    with patch.object(_mod, "_get", _make_mock_get()):
        key = _mod.find_session(2024, "monaco")
    assert key == _SESSION_KEY


def test_find_session_no_match_raises():
    with patch.object(_mod, "_get", lambda path, params=None: []):
        with pytest.raises(ValueError, match="No OpenF1 session"):
            _mod.find_session(2024, "Atlantis")
