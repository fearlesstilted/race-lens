"""Replay API: serve race state from ingested event files.

    uvicorn racelens.api:app --reload

Sessions are .jsonl files in RACELENS_FIXTURES (default: ./fixtures).
Spoiler-free by construction: every response is built only from events
at or before the requested timestamp.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from racelens.adapters.openf1_adapter import (
    OpenF1IncrementalIngester,
    find_session,
    ingest_openf1,
    list_sessions as _openf1_list_sessions,
)
from racelens.commentary.feed import render_feed
from racelens.events_significant import significant_events
from racelens.commentary.renderer import render_all
from racelens.driver_of_day import driver_of_day as _driver_of_day
from racelens.events.models import load_jsonl
from racelens.highlights import highlights as _highlights
from racelens.forecast.overtake import overtake_probability
from racelens.forecast.pit_sim import simulate_pit
from racelens.forecast.projection import project_order
from racelens.forecast.what_if import VALID_SCENARIOS, what_if
from racelens.forecast.win_prob import win_probability
from racelens.insights.battles import detect_battles
from racelens.insights.registry import detect_all
from racelens.live.runner import LiveRunner
from racelens.live.signalr import SignalRCapture, make_signalr_fetch
from racelens.replay.engine import ReplayEngine

FIXTURES_DIR = Path(os.environ.get("RACELENS_FIXTURES", "fixtures"))

# Global live runner — None when no live session is active.
_live: Optional[LiveRunner] = None

# Capture subprocess for source=signalr live sessions (None otherwise).
_capture: Optional[SignalRCapture] = None

# Lock to prevent concurrent start requests.
_start_lock: asyncio.Lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _live is not None:
        _live.stop()
    if _capture is not None:
        _capture.stop()


app = FastAPI(title="Race Lens", version="0.1.0", lifespan=lifespan)


# Formation-lap lead. Race events are shifted forward by this so the formation
# lap occupies display time [0, LIGHTS_OUT_MS) and lights-out = LIGHTS_OUT_MS.
# Keeps the whole timeline non-negative. Must match PRE_START_MS (positions/track.py) and
# LEAD_MS (rust race-core) so the map telemetry and events line up at lights-out.
LIGHTS_OUT_MS = 180_000


@lru_cache(maxsize=8)
def _engine_cached(session_id: str, fixtures_dir: str) -> ReplayEngine:
    fixtures_dir_path = Path(fixtures_dir)
    path = fixtures_dir_path / f"{session_id}.jsonl"
    if not path.is_file():
        raise HTTPException(404, f"session '{session_id}' not found")
    events = load_jsonl(path.read_text(encoding="utf-8"))
    # Only sessions with formation-lap telemetry (a positions.json) get the lead
    # shift; others keep lights-out at 0 (no empty pre-roll).
    if (fixtures_dir_path / f"{session_id}.positions.json").is_file():
        for e in events:
            e.session_time_ms += LIGHTS_OUT_MS
    return ReplayEngine(events)


def _engine(session_id: str) -> ReplayEngine:
    """Thin wrapper so the cache key includes FIXTURES_DIR (read at call time).

    Keeps monkeypatched FIXTURES_DIR (tests) from colliding with real cache
    entries — no manual cache_clear() needed across test runs.
    """
    return _engine_cached(session_id, str(FIXTURES_DIR))


@lru_cache(maxsize=4)
def _positions_data_cached(session_id: str, fixtures_dir: str) -> dict | None:
    path = Path(fixtures_dir) / f"{session_id}.positions.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _positions_data(session_id: str) -> dict | None:
    """Thin wrapper so the cache key includes FIXTURES_DIR (see _engine)."""
    return _positions_data_cached(session_id, str(FIXTURES_DIR))


def _attach_frame(state: dict, session_id: str | None = None) -> dict:
    """Merge per-tick track telemetry into the driver frame in place.

    Single source of x/y+progress: the resampled positions.json (replay). rank
    comes from the engine's official classification (stable, correct race order);
    telemetry `progress` is too noisy to rank by (it can throw a P2 car to P7).
    Live mode (no positions.json) leaves x/y null and the map dead-reckons.

    `session_id` is the fixture stem (used to find positions.json) — NOT
    state["session_id"], which is the internal event session id and differs.
    """
    pos = _positions_data(session_id) if session_id else None
    if pos is None:
        for d in state["drivers"].values():
            d.setdefault("x", None)
            d.setdefault("y", None)
            d.setdefault("progress", None)
        state["frame_source"] = "live"
        state["viewbox"] = None
        return state

    tick_ms = int(pos.get("tick_ms") or 500)
    start_ms = int(pos.get("start_ms") or 0)
    # Both axes are DISPLAY time (events lead-shifted by LIGHTS_OUT_MS, grid already
    # display-time), so no re-shift here — just index the tick.
    tick = round((int(state["at_ms"]) - start_ms) / tick_ms)
    xy = pos.get("drivers", {})
    prog = pos.get("progress", {})
    for drv, d in state["drivers"].items():
        frames = xy.get(drv)
        pt = frames[tick] if frames and 0 <= tick < len(frames) else None
        d["x"], d["y"] = (pt[0], pt[1]) if pt else (None, None)
        pframes = prog.get(drv)
        d["progress"] = pframes[tick] if pframes and 0 <= tick < len(pframes) else None
    state["frame_source"] = "replay"
    state["viewbox"] = pos.get("viewbox", [600, 400])
    return state


def _race_end_ms(eng: ReplayEngine) -> int:
    """End of on-track action = chequered flag (or last lap), NOT the last event.

    Post-race steward messages run minutes past the finish and have no telemetry,
    so using them would leave a dead zone of frozen cars at the end of the
    scrubber. Cap the replay timeline/stream at the finish instead.
    """
    finished = [
        e.session_time_ms for e in eng.events
        if e.type == "SessionStatusChanged" and e.payload.get("status") == "finished"
    ]
    if finished:
        return max(finished)
    laps = [e.session_time_ms for e in eng.events if e.type == "LapCompleted"]
    if laps:
        return max(laps)
    return eng.events[-1].session_time_ms if eng.events else 0

def _clamp_at_ms(at_ms: int) -> int:
    """Negative at_ms = formation lap (telemetry-only, before lights-out).

    There are no events yet at negative timestamps, so callers clamp to 0
    when querying engine state, while the response still echoes the raw
    requested at_ms so the frontend scrubber playhead stays correct.
    """
    return max(0, at_ms)


@app.get("/api/ping")
def ping():
    return {"status": "ok"} #keepalive ping for render demo page 


@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    out = []
    files = sorted(
        FIXTURES_DIR.glob("*.jsonl"),
        key=lambda f: (
            not (FIXTURES_DIR / f"{f.stem}.positions.json").is_file(),
            f.stem,
        ),
    )
    for f in files:
        out.append({"session_id": f.stem})
    return out


@app.get("/api/sessions/{session_id}/state")
def state(session_id: str, at_ms: int = Query()) -> dict:
    # Negative at_ms = formation lap (telemetry-only, before lights-out). There are
    # no events yet, so show the grid (state at 0) but echo the requested time so
    # the scrubber playhead stays in the pre-start window.
    result = _engine(session_id).state_at(_clamp_at_ms(at_ms))
    result["at_ms"] = at_ms
    return _attach_frame(result, session_id)


@app.get("/api/sessions/{session_id}/insights")
def insights(session_id: str, at_ms: int = Query()) -> dict:
    """Active insights at a timestamp, computed from state <= at_ms only."""
    state = _engine(session_id).state_at(_clamp_at_ms(at_ms))
    return {"at_ms": at_ms, "insights": detect_all(state)}


@app.get("/api/sessions/{session_id}/battles")
def battles(session_id: str, at_ms: int = Query()) -> dict:
    """On-track battles at a timestamp: pairs of neighbouring drivers in a real fight."""
    state = _engine(session_id).state_at(_clamp_at_ms(at_ms))
    return {"at_ms": at_ms, "battles": detect_battles(state)}


@app.get("/api/sessions/{session_id}/commentary")
def commentary(session_id: str, at_ms: int = Query(), lang: str = "en", level: str = "pro") -> dict:
    """Active insights rendered as text. lang: en|ru, level: beginner|pro."""
    state = _engine(session_id).state_at(_clamp_at_ms(at_ms))
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
    end_ms = _race_end_ms(eng)

    async def gen():
        t = from_ms
        while True:
            cur = min(t, end_ms)  # always emit the final state exactly at end_ms
            state = _attach_frame(eng.state_at(cur), session_id)
            state["active_insights"] = detect_all(state)
            state["commentary"] = render_all(state["active_insights"], lang, level)
            yield f"data: {json.dumps(state)}\n\n"
            if cur >= end_ms:
                break
            await asyncio.sleep(tick_ms / 1000.0 / speed)
            t += tick_ms
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── Near-live endpoints ───────────────────────────────────────────────────────


@app.post("/api/live/start")
async def live_start(
    year: int = Query(...),
    country: str = Query(...),
    session: str = Query(default="Race"),
    poll_s: float = Query(default=12.0, gt=0),
    source: str = Query(default="openf1", pattern="^(openf1|signalr)$"),
) -> dict:
    """Start the live pipeline.

    source=openf1: find the OpenF1 session and poll it (needs realtime tier
    for actually-live data). Works for historical sessions too.
    source=signalr: record the FREE official F1 SignalR feed via a capture
    subprocess and re-ingest the growing recording each poll. `country` is the
    FastF1 Grand Prix name here (e.g. "Silverstone"). The recording survives
    at fixtures/_capture_*.txt — post-race `racelens ingest-live` turns it
    into a replay fixture even if live mode misbehaves.
    """
    global _live, _capture
    async with _start_lock:
        if _live is not None and _live.is_running:
            raise HTTPException(409, "A live session is already running. Stop it first.")

        if source == "signalr":
            feed_path = FIXTURES_DIR / f"_capture_{year}_{country.lower().replace(' ', '_')}_{session.lower()}.txt"
            _capture = SignalRCapture(feed_path)
            _capture.start()
            fetch = make_signalr_fetch(feed_path, year, country, session)
            _live = LiveRunner(fetch, poll_interval_s=max(poll_s, 5.0))
            await _live.start()
            return {
                "source": "signalr", "feed_file": str(feed_path),
                "poll_interval_s": max(poll_s, 5.0), "status": "started",
            }

        try:
            session_key = find_session(year, country, session)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

        ingester = OpenF1IncrementalIngester(session_key)
        _live = LiveRunner(ingester.fetch, poll_interval_s=poll_s)
        await _live.start()
    return {"session_key": session_key, "poll_interval_s": poll_s, "status": "started"}


@app.get("/api/live/status")
async def live_status() -> dict:
    if _live is None:
        raise HTTPException(404, "No live session active")
    status = _live.status()
    if _capture is not None:
        status["capture_alive"] = _capture.alive
    return status


@app.get("/api/live/stream")
async def live_stream(
    tick_s: float = Query(default=2.0, gt=0),
    lang: str = "en",
    level: str = "pro",
) -> StreamingResponse:
    """SSE stream: emits state_now() every *tick_s* seconds."""
    if _live is None:
        raise HTTPException(404, "No live session active")

    async def gen():
        while True:
            if _live is None or not _live.is_running:
                # Runner stopped — signal end to the client and close the stream.
                yield "event: end\ndata: {}\n\n"
                return
            if _live.engine is None:
                # Runner alive but no data yet — send empty heartbeat and keep waiting.
                yield "data: {}\n\n"
            else:
                state = _attach_frame(_live.state_now())
                state["active_insights"] = detect_all(state)
                state["commentary"] = render_all(state["active_insights"], lang, level)
                yield f"data: {json.dumps(state)}\n\n"
            await asyncio.sleep(tick_s)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/live/stop")
async def live_stop() -> dict:
    global _live, _capture
    if _live is None:
        raise HTTPException(404, "No live session active")
    final_status = _live.status()
    _live.stop()
    _live = None
    if _capture is not None:
        _capture.stop()
        _capture = None
    return final_status


@app.post("/api/replays/download")
def download_replay(
    year: int = Query(...),
    country: str = Query(...),
    session: str = Query(default="Race"),
) -> dict:
    """Download a session from OpenF1 and save it as a replay fixture.

    Fetches the full session, writes it to
    ``fixtures/<country>_<year>_<session>.jsonl`` (lowercased, spaces → _),
    and returns ``{session_id, events, path}``.

    Errors:
    - 404: session not found in OpenF1 (find_session raised ValueError).
    - 502: OpenF1 unavailable (network or HTTP error).
    """
    import re
    import urllib.error

    from racelens.events.models import dump_jsonl

    try:
        session_key = find_session(year, country, session)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        # find_session also hits OpenF1, so it can throttle/network-fail too.
        raise HTTPException(502, f"OpenF1 unavailable: {exc}") from exc

    try:
        events = ingest_openf1(session_key)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise HTTPException(502, f"OpenF1 unavailable: {exc}") from exc

    # Build slug: lowercase, normalise non-alphanumeric runs to underscore
    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    slug = f"{_slug(country)}_{year}_{_slug(session)}"
    out_path = FIXTURES_DIR / f"{slug}.jsonl"
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dump_jsonl(events), encoding="utf-8")

    # Invalidate the engine cache so the new fixture is immediately available
    # (this can overwrite an existing fixture at the same session_id + FIXTURES_DIR).
    _engine_cached.cache_clear()

    return {"session_id": slug, "events": len(events), "path": str(out_path)}


@app.get("/api/live/sessions")
def live_sessions(
    year: int = Query(...),
    country: Optional[str] = Query(default=None),
) -> list[dict]:
    """List sessions for a given year (and optional country) from OpenF1.

    Returns a list sorted by date_start.  Each item includes a `started` flag
    that is True when the current UTC time is >= date_start.
    """
    import urllib.error

    try:
        return _openf1_list_sessions(year, country)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise HTTPException(502, "OpenF1 unavailable") from exc


@app.get("/api/sessions/{session_id}/win-prob")
def win_prob(
    session_id: str,
    at_ms: int = Query(),
):
    """Win probability for every driver at a given timestamp."""
    engine = _engine(session_id)
    state = engine.state_at(_clamp_at_ms(at_ms))
    return win_probability(state, session_id)


@app.get("/api/sessions/{session_id}/win-prob-series")
def win_prob_series(
    session_id: str,
    until_ms: int = Query(ge=0),
    samples: int = Query(default=20, ge=2, le=100),
):
    """Win probability series up to until_ms in N evenly-spaced samples.

    Returns [{at_ms, probs: {driver: prob}}] ascending by at_ms.
    """
    engine = _engine(session_id)
    start_ms = engine.events[0].session_time_ms if engine.events else 0
    if until_ms <= start_ms:
        return []

    step = max(1, (until_ms - start_ms) // (samples - 1))
    points = list(range(start_ms, until_ms, step))
    if not points or points[-1] < until_ms:
        points.append(until_ms)
    # Deduplicate and cap
    points = sorted(set(points))

    result = []
    for t in points:
        state = engine.state_at(t)
        wp = win_probability(state, session_id)
        result.append({"at_ms": t, "probs": wp["win_prob"]})
    return result


@app.get("/api/sessions/{session_id}/forecast")
def forecast(
    session_id: str,
    at_ms: int = Query(),
    laps: int = Query(default=10, ge=1, le=50),
):
    engine = _engine(session_id)
    state = engine.state_at(_clamp_at_ms(at_ms))
    return project_order(state, laps_ahead=laps)


@app.get("/api/sessions/{session_id}/simulate-pit")
def simulate_pit_endpoint(
    session_id: str,
    at_ms: int = Query(),
    driver: str = Query(...),
):
    engine = _engine(session_id)
    state = engine.state_at(_clamp_at_ms(at_ms))
    return simulate_pit(state, driver, session_id)


@app.get("/api/sessions/{session_id}/what-if")
def what_if_endpoint(
    session_id: str,
    at_ms: int = Query(),
    scenario: str = Query(...),
    driver: Optional[str] = Query(default=None),
):
    """Counterfactual race-finish projection.

    scenario: baseline | pit_now | stay_out | no_safety_car
    driver: required for pit_now / stay_out
    """
    if scenario not in VALID_SCENARIOS:
        raise HTTPException(422, f"Invalid scenario '{scenario}'. Valid: {sorted(VALID_SCENARIOS)}")
    if scenario in {"pit_now", "stay_out"} and not driver:
        raise HTTPException(400, f"scenario='{scenario}' requires driver parameter")
    engine = _engine(session_id)
    state = engine.state_at(_clamp_at_ms(at_ms))
    try:
        return what_if(state, session_id, scenario, driver)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/sessions/{session_id}/overtake")
def overtake_endpoint(
    session_id: str,
    at_ms: int = Query(),
    ahead: str = Query(...),
    behind: str = Query(...),
):
    engine = _engine(session_id)
    state = engine.state_at(_clamp_at_ms(at_ms))
    return overtake_probability(state, ahead, behind, session_id)


@app.get("/api/sessions/{session_id}/track")
def track(session_id: str) -> dict:
    """Return pre-computed track outline as {session_id, viewbox, points}."""
    path = FIXTURES_DIR / f"{session_id}.track.json"
    if not path.is_file():
        raise HTTPException(404, f"track data for '{session_id}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/sessions/{session_id}/positions")
def positions(session_id: str) -> dict:
    """Return resampled car positions from Rust race-core pipeline.

    Format: {session_id, start_ms, tick_ms, viewbox, drivers: {DRV: [[x,y]|null, ...]}}
    404 if positions.json has not been generated yet.
    """
    path = FIXTURES_DIR / f"{session_id}.positions.json"
    if not path.is_file():
        raise HTTPException(404, f"positions data for '{session_id}' not found — run the pipeline")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/sessions/{session_id}/feed")
def feed(
    session_id: str,
    until_ms: int = Query(),
    lang: str = "en",
    limit: int = 30,
) -> list:
    """Event feed for the frontend: spoiler-free, newest-first human-readable items."""
    eng = _engine(session_id)
    return render_feed(eng.events, max(0, until_ms), lang=lang, limit=limit)


@app.get("/api/sessions/{session_id}/markers")
def markers(
    session_id: str,
    until_ms: Optional[int] = Query(default=None),
) -> dict:
    """Significant race events for timeline markers and highlight summaries.

    Spoiler-free: pass until_ms to restrict to events at or before that timestamp.
    Without until_ms the full race is returned.
    """
    eng = _engine(session_id)
    clamped = max(0, until_ms) if until_ms is not None else None
    return {"markers": significant_events(eng.events, until_ms=clamped, state_engine=eng)}


@app.get("/api/sessions/{session_id}/highlights")
def get_highlights(
    session_id: str,
    top_n: int = Query(default=8, ge=1, le=50),
) -> dict:
    """Top-N most dramatic moments of the race, sorted chronologically.

    Suitable for a 'race in 60 seconds' highlight reel.
    """
    eng = _engine(session_id)
    return {"highlights": _highlights(eng.events, eng, top_n=top_n)}


@app.get("/api/sessions/{session_id}/driver-of-day")
def get_driver_of_day(session_id: str, at_ms: Optional[int] = Query(default=None)) -> dict:
    """Algorithmic Driver of the Day: top candidates ranked by performance score.

    Pass at_ms for a spoiler-free provisional pick from the race so far (used when
    the panel unlocks in the final laps). Omit for the full-race result.
    """
    eng = _engine(session_id)
    return _driver_of_day(eng.events, eng, at_ms=None if at_ms is None else _clamp_at_ms(at_ms))


@app.get("/api/sessions/{session_id}/timeline")
def timeline(session_id: str) -> dict:
    """Replay bounds + lap markers for the scrubber. No future-revealing
    detail beyond what a replay slider inherently needs."""
    eng = _engine(session_id)
    lap_marks = {}
    for e in eng.events:
        if e.type == "LapCompleted" and e.lap and e.lap not in lap_marks:
            lap_marks[e.lap] = e.session_time_ms
    start_ms = eng.events[0].session_time_ms if eng.events else 0
    # The formation lap lives only in telemetry. When a positions.json exists the
    # events are lead-shifted (see _engine), so lights-out = LIGHTS_OUT_MS and the
    # scrubber starts at the formation origin from positions.json. Without it there
    # is no formation: lights-out stays at 0.
    pos_path = FIXTURES_DIR / f"{session_id}.positions.json"
    lights_out_ms = 0
    if pos_path.is_file():
        lights_out_ms = LIGHTS_OUT_MS
        try:
            pos_start = int(json.loads(pos_path.read_text(encoding="utf-8")).get("start_ms", 0))
            start_ms = min(start_ms, pos_start)
        except (ValueError, KeyError, TypeError):
            pass
    return {
        "session_id": session_id,
        "start_ms": start_ms,
        "end_ms": _race_end_ms(eng),
        "lights_out_ms": lights_out_ms,
        "events_total": len(eng.events),
        "lap_marks": lap_marks,
    }


@app.get("/api/sessions/{session_id}/stints")
def stints(session_id: str) -> dict:
    """Per-driver tyre stint timeline (compound + lap range) for the strategy view."""
    from racelens.tyre_stints import stint_timeline

    eng = _engine(session_id)
    end_ms = eng.events[-1].session_time_ms if eng.events else 0
    final = eng.state_at(end_ms)
    total_laps = final.get("total_laps") or final.get("lap") or 0
    return {
        "session_id": session_id,
        "total_laps": total_laps,
        "stints": stint_timeline(eng.events, total_laps),
    }
