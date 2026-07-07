"""Tests for the direct SignalR feed → Event adapter (live team-radio bits)."""
from racelens.adapters.f1live_adapter import ingest_f1live
from racelens.commentary.feed import render_feed

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
    assert r.payload["audio_path"] == _RADIO_PATH
    assert r.payload["audio_url"] == f"https://livetiming.formula1.com/static/{_SESSION_PATH}{_RADIO_PATH}"


def test_render_feed_carries_audio_url(tmp_path):
    events = ingest_f1live(_write_feed(tmp_path), session_id="test")
    feed = render_feed(events, until_ms=10_000_000)
    radio_items = [i for i in feed if i.get("audio_url")]
    assert len(radio_items) == 1
    assert radio_items[0]["audio_url"].startswith("https://livetiming.formula1.com/static/")
