"""Replay API: serve race state from ingested event files.

    uvicorn racelens.api:app --reload

Sessions are .jsonl files in RACELENS_FIXTURES (default: ./fixtures).
Spoiler-free by construction: every response is built only from events
at or before the requested timestamp.
"""
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException

from racelens.events.models import load_jsonl
from racelens.replay.engine import ReplayEngine

FIXTURES_DIR = Path(os.environ.get("RACELENS_FIXTURES", "fixtures"))

app = FastAPI(title="Race Lens", version="0.1.0")


@lru_cache(maxsize=8)
def _engine(session_id: str) -> ReplayEngine:
    path = FIXTURES_DIR / f"{session_id}.jsonl"
    if not path.is_file():
        raise HTTPException(404, f"session '{session_id}' not found")
    return ReplayEngine(load_jsonl(path.read_text(encoding="utf-8")))


@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    out = []
    for f in sorted(FIXTURES_DIR.glob("*.jsonl")):
        out.append({"session_id": f.stem})
    return out


@app.get("/api/sessions/{session_id}/state")
def state(session_id: str, at_ms: int) -> dict:
    return _engine(session_id).state_at(at_ms)


@app.get("/api/sessions/{session_id}/timeline")
def timeline(session_id: str) -> dict:
    """Replay bounds + lap markers for the scrubber. No future-revealing
    detail beyond what a replay slider inherently needs."""
    eng = _engine(session_id)
    lap_marks = {}
    for e in eng.events:
        if e.type == "LapCompleted" and e.lap and e.lap not in lap_marks:
            lap_marks[e.lap] = e.session_time_ms
    return {
        "session_id": session_id,
        "start_ms": eng.events[0].session_time_ms if eng.events else 0,
        "end_ms": eng.events[-1].session_time_ms if eng.events else 0,
        "events_total": len(eng.events),
        "lap_marks": lap_marks,
    }
