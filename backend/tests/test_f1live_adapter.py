"""Tests for the direct SignalR feed → Event adapter (live team-radio bits)."""
import json

from racelens.adapters.f1live_adapter import ingest_f1live
from racelens.commentary.feed import render_feed
from racelens.replay.engine import ReplayEngine

_SESSION_PATH = "2026/2026-07-05_British_Grand_Prix/2026-07-05_Race/"
_RADIO_PATH = "TeamRadio/HAMILTONLEWIS_44_20260705_1505.mp3"

_LINES = [
    # Keyframe: session info carries the static-file path prefix.
    "['SessionInfo', '{\"Path\": \"%s\"}', '']" % _SESSION_PATH,
    # Timestamped SessionStatus 'Started' anchors t0.
    "['SessionStatus', {'Status': 'Started'}, '2026-07-05T15:00:00.000Z']",
    # Driver number → abbreviation.
    "['DriverList', {'44': {'Tla': 'HAM'}}, '2026-07-05T15:00:01.000Z']",
    # Team radio capture for HAM.
    (
        "['TeamRadio', {'Captures': {'0': {'Utc': '2026-07-05T15:05:00.000Z', "
        "'RacingNumber': '44', 'Path': '%s'}}}, '2026-07-05T15:05:00.500Z']" % _RADIO_PATH
    ),
]


def _write_feed(tmp_path):
    feed = tmp_path / "feed.txt"
    feed.write_text("\n".join(_LINES) + "\n", encoding="utf-8")
    return str(feed)


def test_team_radio_gets_absolute_audio_url_and_lap(tmp_path):
    events = ingest_f1live(_write_feed(tmp_path), session_id="test")
    radio = [e for e in events if e.payload.get("category") == "Radio"]
    assert len(radio) == 1
    r = radio[0]
    assert r.driver_id == "HAM"
    assert r.lap == 1
    assert r.session_time_ms == 300_000
    assert r.payload["audio_path"] == _RADIO_PATH
    assert r.payload["audio_url"] == f"https://livetiming.formula1.com/static/{_SESSION_PATH}{_RADIO_PATH}"


def test_render_feed_carries_audio_url(tmp_path):
    events = ingest_f1live(_write_feed(tmp_path), session_id="test")
    feed = render_feed(events, until_ms=10_000_000)
    radio_items = [i for i in feed if i.get("audio_url")]
    assert len(radio_items) == 1
    assert radio_items[0]["audio_url"].startswith("https://livetiming.formula1.com/static/")


# ── Session badge: Meeting.Location + session Name → state["session_name"] ────

_SESSION_INFO_PAYLOAD = {
    "Meeting": {"Name": "British Grand Prix", "Location": "Silverstone"},
    "Name": "Race",
    "Path": _SESSION_PATH,
}


def _write_session_info_feed(tmp_path):
    lines = [
        "['SessionInfo', %s, '']" % json.dumps(json.dumps(_SESSION_INFO_PAYLOAD)),
        "['SessionStatus', {'Status': 'Started'}, '2026-07-05T15:00:00.000Z']",
    ]
    feed = tmp_path / "feed.txt"
    feed.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(feed)


def test_session_started_carries_session_name(tmp_path):
    events = ingest_f1live(_write_session_info_feed(tmp_path), session_id="test")
    started = [e for e in events if e.type == "SessionStarted"]
    assert len(started) == 1
    assert started[0].payload.get("session_name") == "SILVERSTONE · RACE"


def test_session_name_lands_in_engine_state(tmp_path):
    events = ingest_f1live(_write_session_info_feed(tmp_path), session_id="test")
    state = ReplayEngine(events).state_at(0)
    assert state["session_name"] == "SILVERSTONE · RACE"


def test_session_name_absent_when_no_session_info(tmp_path):
    """Feeds without Meeting/Name (e.g. the radio fixture above, which only
    carries Path) must not crash and leave session_name unset."""
    events = ingest_f1live(_write_feed(tmp_path), session_id="test")
    state = ReplayEngine(events).state_at(0)
    assert state["session_name"] is None


def test_keyframe_is_anchored_to_first_live_timestamp(tmp_path):
    lines = [
        "['SessionData', {\"StatusSeries\": [{\"SessionStatus\": \"Started\", "
        "\"Utc\": \"2026-07-05T15:00:00.000Z\"}]}, '']",
        "['DriverList', {'44': {'Tla': 'HAM'}}, '']",
        "['TimingAppData', {'Lines': {'44': {'Stints': "
        "[{'Compound': 'MEDIUM', 'TotalLaps': 3}]}}}, '']",
        "['TimingData', {'Lines': {'44': {'Position': '1'}}}, "
        "'2026-07-05T15:05:00.000Z']",
    ]
    feed = tmp_path / "midjoin.txt"
    feed.write_text("\n".join(lines) + "\n", encoding="utf-8")

    events = ingest_f1live(str(feed), session_id="test")
    tyre = next(e for e in events if e.type == "TyreStintUpdated")
    assert tyre.session_time_ms == 300_000


def test_race_control_keyframe_uses_each_message_timestamp(tmp_path):
    lines = [
        "['SessionData', {\"StatusSeries\": [{\"SessionStatus\": \"Started\", "
        "\"Utc\": \"2026-07-05T15:00:00.000Z\"}]}, '']",
        "['RaceControlMessages', {'Messages': {"
        "'0': {'Utc': '2026-07-05T15:01:00.000Z', 'Category': 'Other', "
        "'Message': 'FIRST'}, "
        "'1': {'Utc': '2026-07-05T15:02:00.000Z', 'Category': 'Other', "
        "'Message': 'SECOND'}}}, '']",
        "['TimingData', {'Lines': {'44': {'Position': '1'}}}, "
        "'2026-07-05T15:05:00.000Z']",
    ]
    feed = tmp_path / "midjoin.txt"
    feed.write_text("\n".join(lines) + "\n", encoding="utf-8")

    messages = [
        event for event in ingest_f1live(str(feed), session_id="test")
        if event.type == "RaceControlMessage"
    ]
    assert [(event.session_time_ms, event.payload["message"]) for event in messages] == [
        (60_000, "FIRST"),
        (120_000, "SECOND"),
    ]
