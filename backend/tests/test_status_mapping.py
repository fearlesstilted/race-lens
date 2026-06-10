"""Tests for shared status mapping and adapter-specific edge cases."""
from __future__ import annotations

from unittest.mock import patch

import pytest

import racelens.adapters.openf1_adapter as _of1
from racelens.adapters._common import STATUS_TABLE, message_to_status


# ── message_to_status helper ──────────────────────────────────────────────────

def test_chequered_flag_gives_finished():
    assert message_to_status("CHEQUERED FLAG") == "finished"


def test_chequered_flag_case_insensitive():
    assert message_to_status("chequered flag") == "finished"


def test_red_flag_gives_red_flag():
    assert message_to_status("RED FLAG") == "red_flag"


def test_chequered_flag_not_red_flag():
    """'CHEQUERED FLAG' contains 'RED FLAG' as a substring.  The correct status
    must be 'finished', not 'red_flag' — verifying CHEQUERED comes first."""
    result = message_to_status("CHEQUERED FLAG")
    assert result == "finished", (
        f"'CHEQUERED FLAG' mapped to {result!r}; expected 'finished' — "
        "check that CHEQUERED FLAG precedes RED FLAG in STATUS_TABLE"
    )


def test_vsc_message():
    assert message_to_status("VIRTUAL SAFETY CAR DEPLOYED") == "vsc"


def test_sc_deployed():
    assert message_to_status("SAFETY CAR DEPLOYED") == "safety_car"


def test_green_light():
    assert message_to_status("GREEN LIGHT - PIT EXIT OPEN") == "started"


def test_track_clear():
    assert message_to_status("TRACK CLEAR") == "started"


def test_unknown_message_returns_none():
    assert message_to_status("DEBRIS ON TRACK") is None


def test_status_table_chequered_before_red_flag():
    """Structural check: 'CHEQUERED FLAG' must appear before 'RED FLAG' in
    STATUS_TABLE so that first-match semantics produce the correct result."""
    needles = [needle for needle, _ in STATUS_TABLE]
    assert "CHEQUERED FLAG" in needles, "CHEQUERED FLAG missing from STATUS_TABLE"
    assert "RED FLAG" in needles, "RED FLAG missing from STATUS_TABLE"
    assert needles.index("CHEQUERED FLAG") < needles.index("RED FLAG"), (
        "CHEQUERED FLAG must come before RED FLAG in STATUS_TABLE"
    )


# ── OpenF1 adapter: lap_duration=null ────────────────────────────────────────

_SESSION_KEY = 9999

_SESSIONS_STUB = [
    {
        "session_key": _SESSION_KEY,
        "session_name": "Race",
        "year": 2024,
        "location": "TestCircuit",
        "country_name": "Testland",
        "circuit_short_name": "TST",
    }
]

_DRIVERS_STUB = [{"driver_number": 1, "name_acronym": "VER"}]


def _make_lap_null_duration_mock():
    data = {
        "/sessions": _SESSIONS_STUB,
        "/drivers": _DRIVERS_STUB,
        "/laps": [
            # Lap 1 with valid duration — establishes t0
            {"driver_number": 1, "lap_number": 1,
             "date_start": "2024-05-26T13:00:00.000", "lap_duration": 80.0},
            # Lap 2 with null duration — should not crash; lap_time_ms=None
            {"driver_number": 1, "lap_number": 2,
             "date_start": "2024-05-26T13:01:20.000", "lap_duration": None},
        ],
        "/position": [],
        "/pit": [],
        "/stints": [],
        "/intervals": [],
        "/race_control": [],
    }
    return lambda path, params=None: list(data.get(path, []))


def test_lap_null_duration_does_not_crash():
    """A lap row with lap_duration=null must not raise and must produce a
    LapCompleted event with lap_time_ms=None (t_end = date_start)."""
    with patch.object(_of1, "_get", _make_lap_null_duration_mock()):
        events = _of1.ingest_openf1(_SESSION_KEY)

    lap2_events = [
        e for e in events
        if e.type == "LapCompleted" and e.lap == 2 and e.driver_id == "VER"
    ]
    assert len(lap2_events) == 1, "Expected exactly one LapCompleted for lap 2"
    lc = lap2_events[0]
    assert lc.payload.get("lap_time_ms") is None, (
        f"Expected lap_time_ms=None for null duration, got {lc.payload.get('lap_time_ms')!r}"
    )
    # t_end should be date_start rebased to session ms (non-negative)
    assert lc.session_time_ms >= 0
