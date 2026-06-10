# Frontend plan — Race Lens web app (handoff for Codex)

Goal: a **web** replay companion (Vite + React + TypeScript) consuming the
existing backend. No desktop shells, no Electron/Tauri — this must be a URL
you can put in a portfolio. Dark theme, no heavy design system; plain CSS
modules or Tailwind, your pick.

The backend is DONE for your scope and covered by tests — do not modify
`backend/`. If the API seems wrong, write it down in `NOTES.md` and work
around it; don't fix it yourself.

## Run the backend

```bash
cd backend
pip install -e ".[dev,api]"
pytest                       # 16 passed = your contract is intact
RACELENS_FIXTURES=fixtures uvicorn racelens.api:app --port 8000
```

If `fixtures/` has no real session yet, generate the mini fixture:

```bash
python - <<'EOF'
import sys; sys.path.insert(0, "tests")
from pathlib import Path
from test_replay import mini_race
from racelens.events.models import dump_jsonl
Path("fixtures").mkdir(exist_ok=True)
Path("fixtures/2024_mini_race.jsonl").write_text(dump_jsonl(mini_race()))
EOF
```

(Real Monaco fixture: `python -m racelens.cli ingest 2024 Monaco R -o fixtures/2024_monaco_r.jsonl` — separate task, needs `pip install -e ".[fastf1]"`.)

## API contract (all GET, JSON)

### `/api/sessions`
```json
[{"session_id": "2024_mini_race"}]
```

### `/api/sessions/{id}/timeline`
```json
{"session_id": "2024_mini_race", "start_ms": 0, "end_ms": 250000,
 "events_total": 26, "lap_marks": {"1": 80000, "2": 160000, "3": 238000}}
```

### `/api/sessions/{id}/state?at_ms=140000`
```json
{"session_id": "...", "at_ms": 140000, "lap": 1, "session_status": "started",
 "total_laps": 3, "classification": ["VER", "NOR", "LEC"],
 "drivers": {"VER": {"position": 1, "laps_completed": 1, "last_lap_ms": 78000,
   "best_lap_ms": 78000, "gap_s": null, "interval_s": null,
   "tyre_compound": "M", "tyre_age_laps": 1, "pit_count": 0, "in_pit": false}, "...": {}},
 "data_quality": {"status": "good", "last_event_ms": 136000,
   "events_applied": 18, "duplicates_dropped": 0}}
```

### `/api/sessions/{id}/insights?at_ms=247000`
```json
{"at_ms": 247000, "insights": [{
  "insight_id": "traffic:LEC:247000", "type": "TRAFFIC_RISK_HIGH",
  "severity": "high", "confidence": "high", "created_at_ms": 247000, "lap": 3,
  "driver_ids": ["LEC", "NOR"],
  "evidence": {"interval_s": 0.7, "pace_delta_ms": 2800,
    "behind_last_lap_ms": 77000, "ahead_last_lap_ms": 79800}}]}
```
`driver_ids` = [stuck driver, car ahead]. Render as: "LEC stuck behind NOR,
+2.8s/lap faster, gap 0.7s".

### `/api/sessions/{id}/stream?speed=10&from_ms=0&tick_ms=1000` — SSE
`data:` messages = the same state object as `/state`, plus
`"active_insights": [...]` (same shape as insights). Terminates with
`event: end`. Use native `EventSource`; query params only.

## Architecture

```
src/
  api/client.ts        fetch wrapper + types for the contract above
  api/types.ts         RaceState, Driver, Insight, Timeline (mirror JSON exactly)
  features/
    sessions/          SessionPicker — list from /api/sessions
    replay/            ReplayRoom — the main screen, owns playback state
      useReplay.ts     playback model (see below)
      TimingTable.tsx
      InsightFeed.tsx
      TimelineScrubber.tsx
      PlaybackControls.tsx
  App.tsx              routing: "/" picker → "/session/:id" replay room
```

### Playback model (`useReplay`) — the core piece

Two modes, one state shape:
- **Scrub mode**: user drags the slider → debounced (~150ms) fetch of
  `/state?at_ms=` + `/insights?at_ms=`. Paused by default.
- **Play mode**: open `EventSource` on `/stream?speed=S&from_ms=current`,
  each message replaces the current state. Pause = close the EventSource,
  keep last state. Changing speed = close + reopen from current `at_ms`.

State: `{ state: RaceState | null, insights: Insight[], playing: boolean,
speed: 1|5|10, atMs: number }`. Single source of truth; components are dumb.

## Components

**TimingTable** — rows in `classification` order:
`P | Driver | Laps | Last | Best | Tyre | Age | Pits | Status`.
Format ms → `1:18.000`. Tyre chip colored: S red, M yellow, H white-ish.
Status: `IN PIT` badge when `in_pit`, otherwise blank.

**InsightFeed** — card per active insight: severity color strip
(high=red, medium=amber), headline from `driver_ids`, evidence line from
`evidence` fields. Empty state: "No active insights".

**TimelineScrubber** — range input from `start_ms` to `end_ms`, ticks at
`lap_marks` values with lap numbers. Shows current lap / total_laps.

**PlaybackControls** — Play/Pause, speed (1x/5x/10x), session status pill,
`data_quality.status` dot (good=green, stale=amber, unknown=grey).

## Milestones — commit after each, in this order

1. **M1**: Vite scaffold, types, client, SessionPicker renders real list.
   Acceptance: `npm run dev` against running backend shows the session.
2. **M2**: ReplayRoom with scrub mode — slider + TimingTable update on drag.
   Acceptance: dragging to 140000 on mini fixture shows VER/NOR/LEC order
   and LEC pit_count 1.
3. **M3**: Play mode via EventSource + PlaybackControls + InsightFeed.
   Acceptance: pressing play at 10x replays mini race in ~25s; traffic
   insight card appears near the end; pause/resume works.
4. **M4**: TimelineScrubber lap marks, tyre chips, polish, empty/error
   states (backend down → readable message, not a blank page).

## Conventions

- Commit as `Fiodar Pysh <m1nzeo09@gmail.com>`, no AI co-author trailers.
- Frontend lives in `frontend/` at repo root.
- Vite dev proxy `/api` → `http://localhost:8000` (no CORS work needed).
- TypeScript strict; no `any` in `api/`.
- No Redux/router libs beyond `react-router-dom`; TanStack Query optional —
  plain fetch + the useReplay hook is fine at this size.
- Do NOT build: track map, telemetry charts, auth, i18n, SSR, tests beyond
  one render smoke test. That's later phases.

## Definition of done

`uvicorn racelens.api:app` + `npm run dev` → pick session → watch the mini
race replay at 10x with live timing table, insight card, working scrubber.
Record a 20s screen capture for the README when it works.
