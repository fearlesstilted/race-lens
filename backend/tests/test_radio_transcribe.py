"""Radio transcription plumbing (model itself is not exercised — too heavy)."""
import json

from racelens.commentary.feed import render_feed
from racelens.events.models import dump_jsonl, event, load_jsonl, make_event_id
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


def test_transcribe_rejects_oversized_radio_clip(monkeypatch) -> None:
    class Model:
        called = False

        def transcribe(self, *_args, **_kwargs):
            self.called = True
            return [], None

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        @staticmethod
        def read(limit):
            assert limit == 5
            return b"12345"

    model = Model()
    monkeypatch.setattr(rt, "MAX_AUDIO_BYTES", 4)
    monkeypatch.setattr(rt, "_model", lambda: model)
    monkeypatch.setattr(rt.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    assert rt.transcribe("https://provider.test/radio.mp3") is None
    assert not model.called


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
    assert got[0]["event_id"] == make_event_id(
        "s", "RaceControlMessage", 1, "HAM", got[0]["payload"]
    )


def test_enrich_fixture_restores_order_after_event_id_changes(tmp_path, monkeypatch) -> None:
    fx = tmp_path / "r.jsonl"
    radio = event(
        "s", "RaceControlMessage", 1, "HAM", category="Radio",
        message="RADIO: HAM", audio_url="https://x/1.mp3",
    )
    other = event("s", "RaceControlMessage", 1, category="Other", message="5")
    fx.write_text(dump_jsonl(sorted([radio, other], key=lambda item: item.event_id)))
    monkeypatch.setattr(rt, "transcribe", lambda url: f"text for {url}")

    rt.enrich_fixture(fx)

    got = load_jsonl(fx.read_text())
    assert got == sorted(got, key=lambda item: (item.session_time_ms, item.event_id))
