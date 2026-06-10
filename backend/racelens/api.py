"""Replay API: serve race state from ingested event files.

    uvicorn racelens.api:app --reload

Sessions are .jsonl files in RACELENS_FIXTURES (default: ./fixtures).
Spoiler-free by construction: every response is built only from events
at or before the requested timestamp.
"""
import asyncio
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from racelens.commentary.renderer import render_all
from racelens.events.models import load_jsonl
from racelens.insights.registry import detect_all
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
def state(session_id: str, at_ms: int = Query(ge=0)) -> dict:
    return _engine(session_id).state_at(at_ms)


@app.get("/api/sessions/{session_id}/insights")
def insights(session_id: str, at_ms: int = Query(ge=0)) -> dict:
    """Active insights at a timestamp, computed from state <= at_ms only."""
    state = _engine(session_id).state_at(at_ms)
    return {"at_ms": at_ms, "insights": detect_all(state)}


@app.get("/api/sessions/{session_id}/commentary")
def commentary(session_id: str, at_ms: int = Query(ge=0), lang: str = "en", level: str = "pro") -> dict:
    """Active insights rendered as text. lang: en|ru, level: beginner|pro."""
    state = _engine(session_id).state_at(at_ms)
    return {"at_ms": at_ms, "items": render_all(detect_all(state), lang, level)}


@app.get("/api/sessions/{session_id}/stream")
async def stream(
    session_id: str, speed: float = 10.0, from_ms: int = 0, tick_ms: int = 1000,
    lang: str = "en", level: str = "pro",
) -> StreamingResponse:
    """Simulated live: replay the session as an SSE stream of states.

    One message per `tick_ms` of session time, paced at `speed`x real time.
    Each message carries full state + active insights, so the frontend
    treats replay and live identically.
    """
    if speed <= 0 or tick_ms <= 0:
        raise HTTPException(422, "speed and tick_ms must be positive")
    eng = _engine(session_id)
    end_ms = eng.events[-1].session_time_ms if eng.events else 0

    async def gen():
        t = from_ms
        while True:
            cur = min(t, end_ms)  # always emit the final state exactly at end_ms
            state = eng.state_at(cur)
            state["active_insights"] = detect_all(state)
            state["commentary"] = render_all(state["active_insights"], lang, level)
            yield f"data: {json.dumps(state)}\n\n"
            if cur >= end_ms:
                break
            await asyncio.sleep(tick_ms / 1000.0 / speed)
            t += tick_ms
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


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
