"""SignalR live-source wiring: capture supervision + fetch guard + endpoint."""
import subprocess
import sys
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from racelens.events.models import event  # noqa: E402
from racelens.live.signalr import SignalRCapture, make_signalr_fetch  # noqa: E402


class SleeperCapture(SignalRCapture):
    """Real subprocess supervision, harmless child (no SignalR in tests)."""

    def start(self):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
        )


def test_capture_supervises_subprocess(tmp_path):
    cap = SleeperCapture(tmp_path / "feed.txt")
    assert not cap.alive
    cap.start()
    assert cap.alive
    cap.stop()
    assert not cap.alive
    cap.stop()  # idempotent
    assert not cap.alive


def test_fetch_returns_empty_while_feed_missing(tmp_path):
    """No file / empty file → [] (capture still connecting), not an exception."""
    feed = tmp_path / "feed.txt"
    fetch = make_signalr_fetch(feed, 2026, "Silverstone", "R")
    assert fetch() == []
    feed.write_text("", encoding="utf-8")
    assert fetch() == []


def test_live_start_signalr_wires_runner_and_capture(tmp_path, monkeypatch):
    """source=signalr: starts capture + runner; state flows; stop kills both."""
    import racelens.api as api

    started: dict = {"capture": 0, "stopped": 0}

    class FakeCapture:
        def __init__(self, out_path, no_auth=False):
            self.out_path = out_path

        def start(self):
            started["capture"] += 1

        def stop(self):
            started["stopped"] += 1

        @property
        def alive(self):
            return started["capture"] > started["stopped"]

    def fake_make_fetch(feed_path, year, gp, session):
        def fetch():
            return [
                event("live_test", "SessionStarted", 0, total_laps=5),
                event("live_test", "PositionChanged", 1000, "VER", position=1),
            ]
        return fetch

    monkeypatch.setattr(api, "SignalRCapture", FakeCapture)
    monkeypatch.setattr(api, "make_signalr_fetch", fake_make_fetch)
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr(api.importlib.util, "find_spec", lambda name: object())

    c = TestClient(api.app)
    r = c.post("/api/live/start", params={
        "year": 2026, "country": "Silverstone", "session": "R",
        "source": "signalr", "poll_s": 6,
    })
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "signalr"
    assert started["capture"] == 1

    try:
        # Wait for the first poll to build the engine, then check the state
        # the /api/live/stream SSE would serve (state_now).
        deadline = time.time() + 5
        while time.time() < deadline and (api._live is None or api._live.engine is None):
            time.sleep(0.05)
        assert api._live is not None and api._live.engine is not None, "runner never built engine"
        state = api._live.state_now()
        assert state["drivers"]["VER"]["position"] == 1
        assert state["drivers"]["VER"]["rank"] == 1

        st = c.get("/api/live/status").json()
        assert st["capture_alive"] is True
    finally:
        stop = c.post("/api/live/stop")
    assert stop.status_code == 200
    assert started["stopped"] == 1
    assert c.get("/api/live/status").status_code == 404


def test_live_feed_returns_items_once_engine_ready(tmp_path, monkeypatch):
    """/api/live/feed renders the accumulated live events (no session_id needed)."""
    import racelens.api as api

    started: dict = {"capture": 0, "stopped": 0}

    class FakeCapture:
        def __init__(self, out_path, no_auth=False):
            self.out_path = out_path

        def start(self):
            started["capture"] += 1

        def stop(self):
            started["stopped"] += 1

        @property
        def alive(self):
            return started["capture"] > started["stopped"]

    def fake_make_fetch(feed_path, year, gp, session):
        def fetch():
            return [
                event("live_test", "SessionStarted", 0, total_laps=5),
                event("live_test", "PositionChanged", 1000, "VER", position=1),
                event(
                    "live_test", "RaceControlMessage", 5000,
                    category="Other", message="TEST PENALTY",
                ),
            ]
        return fetch

    monkeypatch.setattr(api, "SignalRCapture", FakeCapture)
    monkeypatch.setattr(api, "make_signalr_fetch", fake_make_fetch)
    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr(api.importlib.util, "find_spec", lambda name: object())

    c = TestClient(api.app)
    r = c.post("/api/live/start", params={
        "year": 2026, "country": "Silverstone", "session": "R",
        "source": "signalr", "poll_s": 6,
    })
    assert r.status_code == 200, r.text

    try:
        deadline = time.time() + 5
        while time.time() < deadline and (api._live is None or api._live.engine is None):
            time.sleep(0.05)
        assert api._live is not None and api._live.engine is not None, "runner never built engine"

        feed_resp = c.get("/api/live/feed")
        assert feed_resp.status_code == 200, feed_resp.text
        items = feed_resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1
    finally:
        c.post("/api/live/stop")


def test_live_feed_404_without_session():
    import racelens.api as api

    assert api._live is None
    c = TestClient(api.app)
    r = c.get("/api/live/feed")
    assert r.status_code == 404


def test_live_start_rejects_unknown_source(tmp_path, monkeypatch):
    import racelens.api as api

    monkeypatch.setattr(api, "FIXTURES_DIR", tmp_path)
    c = TestClient(api.app)
    r = c.post("/api/live/start", params={
        "year": 2026, "country": "Silverstone", "source": "carrier-pigeon",
    })
    assert r.status_code == 422
