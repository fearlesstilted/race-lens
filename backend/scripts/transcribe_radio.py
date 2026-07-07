"""Whisper spike: download the fixture's team-radio clips, transcribe with two
models, print text + wall time per clip. Decides whether transcription ships.

    python3 scripts/transcribe_radio.py [fixture.jsonl]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://livetiming.formula1.com/static/"
SESSION_PATH = "2026/2026-07-05_British_Grand_Prix/2026-07-05_Race/"
FIXTURE = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures/silverstone_2026_race.jsonl")
CACHE = Path("fixtures/_radio_cache")
MODELS = ["medium", "large-v3"]


def clips() -> list[Path]:
    CACHE.mkdir(exist_ok=True)
    out = []
    for ln in FIXTURE.read_text().splitlines():
        p = json.loads(ln).get("payload", {})
        if p.get("category") != "Radio" or not p.get("audio_path"):
            continue
        dst = CACHE / Path(p["audio_path"]).name
        if not dst.exists():
            url = p.get("audio_url") or BASE + SESSION_PATH + p["audio_path"]
            print(f"↓ {dst.name}", file=sys.stderr)
            urllib.request.urlretrieve(url, dst)
        out.append(dst)
    return out


def main() -> None:
    from faster_whisper import WhisperModel

    files = clips()
    print(f"{len(files)} clips\n")
    for name in MODELS:
        print(f"═══ {name} (int8) ═══")
        model = WhisperModel(name, device="cpu", compute_type="int8")
        total = 0.0
        for f in files:
            t0 = time.time()
            segments, _ = model.transcribe(str(f), language="en", vad_filter=True)
            text = " ".join(s.text.strip() for s in segments)
            dt = time.time() - t0
            total += dt
            print(f"[{dt:5.1f}s] {f.name}: {text}")
        print(f"── total {total:.0f}s ({total / len(files):.1f}s/clip)\n")


if __name__ == "__main__":
    main()
