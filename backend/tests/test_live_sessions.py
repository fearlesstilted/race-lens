"""Tests for GET /api/live/sessions — no real network, all HTTP mocked."""
from __future__ import annotations

import urllib.error
from unittest.mock import patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import racelens.adapters.openf1_adapter as _mod  # noqa: E402
import racelens.api as api  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(api.app)


# ── Canned OpenF1 session rows ────────────────────────────────────────────────

_PAST   = "2026-06-08T13:00:00"   # clearly in the past
_FUTURE = "2099-01-01T15:00:00"   # clearly in the future

_SESSIONS = [
    {
        "session_key": 1001,
        "session_name": "Race",
        "session_type": "Race",
        "date_start": _PAST,
        "year": 2026,
        "country_name": "Austria",
    },
    {
        "session_key": 1002,
        "session_name": "Qualifying",
        "session_type": "Qualifying",
        "date_start": _FUTURE,
        "year": 2026,
        "country_name": "Austria",
    },
    {
        "session_key": 1000,
        "session_name": "Practice 1",
        "session_type": "Practice",
        "date_start": "2026-06-06T10:30:00",
        "year": 2026,
        "country_name": "Austria",
    },
]


def _mock_get(rows):
    """Return a _get stub that always returns *rows* regardless of path/params."""
    def _get(path, params=None):
        return list(rows)
    return _get


def _mock_get_error():
    def _get(path, params=None):
        raise urllib.error.URLError("simulated network error")
    return _get


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_returns_sorted_by_date_start(client):
    with patch.object(_mod, "_get", _mock_get(_SESSIONS)):
        r = client.get("/api/live/sessions", params={"year": 2026, "country": "Austria"})
    assert r.status_code == 200
    items = r.json()
    dates = [item["date_start"] for item in items]
    assert dates == sorted(dates), "Sessions must be sorted by date_start ascending"


def test_started_flag_past_session(client):
    with patch.object(_mod, "_get", _mock_get(_SESSIONS)):
        r = client.get("/api/live/sessions", params={"year": 2026, "country": "Austria"})
    items = r.json()
    race = next(i for i in items if i["session_name"] == "Race")
    assert race["started"] is True, "Past session must have started=True"


def test_started_flag_future_session(client):
    with patch.object(_mod, "_get", _mock_get(_SESSIONS)):
        r = client.get("/api/live/sessions", params={"year": 2026, "country": "Austria"})
    items = r.json()
    qual = next(i for i in items if i["session_name"] == "Qualifying")
    assert qual["started"] is False, "Future session must have started=False"


def test_network_error_returns_502(client):
    with patch.object(_mod, "_get", _mock_get_error()):
        r = client.get("/api/live/sessions", params={"year": 2026})
    assert r.status_code == 502
    assert "unavailable" in r.json()["detail"].lower()


def test_year_only_no_country(client):
    """Omitting country should work — returns all sessions for that year."""
    with patch.object(_mod, "_get", _mock_get(_SESSIONS)):
        r = client.get("/api/live/sessions", params={"year": 2026})
    assert r.status_code == 200
    assert len(r.json()) == len(_SESSIONS)


def test_response_shape(client):
    """Every item must have the required fields."""
    with patch.object(_mod, "_get", _mock_get(_SESSIONS)):
        r = client.get("/api/live/sessions", params={"year": 2026})
    for item in r.json():
        assert "session_name" in item
        assert "session_key" in item
        assert "session_type" in item
        assert "date_start" in item
        assert "started" in item
