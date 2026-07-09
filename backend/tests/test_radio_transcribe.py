"""Radio transcription plumbing (model itself is not exercised — too heavy)."""
import json

from racelens.commentary.feed import render_feed
from racelens.events.models import event
from racelens.radio import transcribe as rt


def test_feed_carries_transcript() -> None:
    e = event(
        "s", "RaceControlMessage", 1000, "HAM",
        category="Radio", message="RADIO: HAM",
        audio_url="https://x/clip.mp3", transcript="box box",
    )
    items = render_feed([e], until_ms=2000)
    radio = [i for i in items if i.get("audio_url")]
    assert radio and radio[0]["transcript"] == "box box"


def test_enrich_fixture_fills_and_skips(tmp_path, monkeypatch) -> None:
    fx = tmp_path / "r.jsonl"
    rows = [
        {"event_id": "a", "session_id": "s", "type": "RaceControlMessage",
         "session_time_ms": 1, "driver_id": "HAM", "source": "fixture",
         "confidence": "high",
         "payload": {"category": "Radio", "message": "RADIO: HAM",
                     "audio_url": "https://x/1.mp3"}},
        {"event_id": "b", "session_id": "s", "type": "RaceControlMessage",
         "session_time_ms": 2, "driver_id": "VER", "source": "fixture",
         "confidence": "high",
         "payload": {"category": "Radio", "message": "RADIO: VER",
                     "audio_url": "https://x/2.mp3", "transcript": "old"}},
        {"event_id": "c", "session_id": "s", "type": "PitIn",
         "session_time_ms": 3, "driver_id": "HAM", "source": "fixture",
         "confidence": "high", "payload": {}},
    ]
    fx.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    monkeypatch.setattr(rt, "transcribe", lambda url: f"text for {url}")
    assert rt.enrich_fixture(fx) == 1  # only the transcript-less radio event

    got = [json.loads(ln) for ln in fx.read_text().splitlines()]
    assert got[0]["payload"]["transcript"] == "text for https://x/1.mp3"
    assert got[1]["payload"]["transcript"] == "old"  # untouched
    assert "transcript" not in got[2]["payload"]
