# Race Lens

[![CI](https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml/badge.svg)](https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Open-source motorsport replay **and prediction** engine.

```
raw motorsport data → normalized event timeline → deterministic race state
   → strategy insights + forward forecast → replay / live UI / API
```

Race Lens normalizes timing data (FastF1, OpenF1) into an immutable event timeline and
deterministically reconstructs race state at any timestamp. On top of that state it does
two things most fan tools don't:

- **Explains the present** — structured strategy insights (traffic, DRS trains, pit
  windows, undercut risk, tyre degradation, clean-air pace) with human commentary in
  English and Russian, no LLM required.
- **Projects the future** — a deterministic forecast layer: projected finishing order,
  live win probability, overtake probability, an interactive **pit-stop / undercut
  simulator**, and **"what-if" counterfactual re-runs** ("what if Leclerc pitted now?").

Replay-first: the same engine drives historical replay, simulated-live, and near-live mode
(polling OpenF1 during a real session). Spoiler-free by construction — state at time `t`
uses only events up to `t`. Plain explainable models throughout; no machine learning.

## Demo

```bash
docker compose up --build
```

Open http://localhost:5173. The Spain 2024 replay ships with ready-made
track positions, so the map works without FastF1, Rust, or preprocessing.

## Architecture

| Layer | What it does | Files |
|---|---|---|
| **Events** | Deterministic IDs, typed envelope, dedupe | [`racelens/events/`](backend/racelens/events/) |
| **Replay engine** | `state_at(t)`, snapshots, no future leakage | [`racelens/replay/`](backend/racelens/replay/) |
| **Insights** | 7 detectors: traffic, DRS train, pit window, undercut, tyre degradation, clean-air pace, SC pit window | [`racelens/insights/`](backend/racelens/insights/) |
| **Forecast** | Projected order, win probability, overtake probability, pit simulator, what-if counterfactuals — explainable, no ML | [`racelens/forecast/`](backend/racelens/forecast/) |
| **Significant events** | Crashes, penalties, lead changes, flags → timeline markers, highlights, driver-of-the-day | [`racelens/events_significant.py`](backend/racelens/events_significant.py) |
| **Commentary** | EN/RU × beginner/pro templates, no AI required | [`racelens/commentary/`](backend/racelens/commentary/) |
| **API / SSE** | FastAPI REST + Server-Sent Events stream + live polling | [`racelens/api.py`](backend/racelens/api.py) |
| **Adapters** | FastF1 and OpenF1 normalized to the same envelope | [`racelens/adapters/`](backend/racelens/adapters/) |
| **race-core** | Rust CLI resampler: raw JSONL → positions.json (500 ms ticks, linear interp, normalised to SVG viewbox) | [`rust/race-core/`](rust/race-core/) |
| **Frontend** | React + TS broadcast UI: timing tower, telemetry track map, insight feed, forecast & projection overlays | [`frontend/src/`](frontend/src/) |

## Quickstart

**Run the replay UI (no FastF1/Rust needed):**

```bash
docker compose up --build
# UI  → http://localhost:5173
# API → http://localhost:8000
```

**Install and test (no network needed):**

```bash
cd backend
pip install -e ".[dev,api]"
python -m pytest -q          # 260+ tests, all pass (race fixtures are committed)
```

**Ingest a session (FastF1):**

```bash
pip install -e ".[dev,api,fastf1]"
python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
python -m racelens.cli state fixtures/monaco_2024_race.jsonl --at-ms 3600000
```

**Full telemetry pipeline (real car positions):**

```bash
# 1. Export track outline (includes extent_dm for Rust normalisation)
python -m racelens.cli track 2024 Monaco R -o fixtures/monaco_2024_race.track.json

# 2. Export raw X/Y telemetry per driver (~43 MB JSONL, temporary)
python -m racelens.cli positions-raw 2024 Monaco R -o fixtures/monaco_2024_race.positions_raw.jsonl

# 3. Resample with Rust race-core (500 ms ticks → 4.7 MB JSON, ~0.2 s)
cd rust/race-core && cargo build --release
./target/release/race-core \
  ../../backend/fixtures/monaco_2024_race.positions_raw.jsonl \
  ../../backend/fixtures/monaco_2024_race.track.json \
  ../../backend/fixtures/monaco_2024_race.positions.json \
  500
```

**Ingest via OpenF1 (near-live source, no extra deps):**

```bash
python -m racelens.cli ingest-openf1 2024 Monaco -o fixtures/monaco_2024_openf1.jsonl
```

**Run the API server:**

```bash
uvicorn racelens.api:app --reload
# → http://localhost:8000/api/sessions
```

**Run the frontend:**

```bash
cd frontend
npm i
npm run dev
# → http://localhost:5173
```

**Docker:**

```bash
docker compose up
# UI at http://localhost:5173, API at http://localhost:8000
# Fixtures mounted from ./backend/fixtures; Spain 2024 includes positions.json
```

## API Endpoints

**State & replay**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions` | List available sessions |
| `GET` | `/api/sessions/{id}/state?at_ms=N` | Race state snapshot at timestamp |
| `GET` | `/api/sessions/{id}/timeline` | Event timeline + lap markers |
| `GET` | `/api/sessions/{id}/track` | Track outline (from telemetry) |
| `GET` | `/api/sessions/{id}/positions` | Resampled car positions for the map |
| `GET` | `/api/sessions/{id}/stream?speed=N` | SSE simulated-live stream |

**Insight & narrative**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions/{id}/insights?at_ms=N` | Structured strategy insights |
| `GET` | `/api/sessions/{id}/battles?at_ms=N` | Active wheel-to-wheel battles |
| `GET` | `/api/sessions/{id}/commentary?at_ms=N&lang=&level=` | Human-readable commentary |
| `GET` | `/api/sessions/{id}/feed?until_ms=N&lang=&limit=` | Spoiler-free event ticker |
| `GET` | `/api/sessions/{id}/markers` | Significant-event timeline markers |
| `GET` | `/api/sessions/{id}/highlights?top_n=N` | Top dramatic moments ("race in 60s") |
| `GET` | `/api/sessions/{id}/driver-of-day` | Computed driver-of-the-day + candidates |

**Forecast (prediction)**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions/{id}/forecast?at_ms=&laps=` | Projected finishing order |
| `GET` | `/api/sessions/{id}/win-prob?at_ms=N` | Win probability per driver |
| `GET` | `/api/sessions/{id}/win-prob-series?until_ms=&samples=` | Win-probability over time |
| `GET` | `/api/sessions/{id}/overtake?at_ms=&ahead=&behind=` | Overtake probability for a pair |
| `GET` | `/api/sessions/{id}/simulate-pit?at_ms=&driver=` | Undercut verdict if driver pits now |
| `GET` | `/api/sessions/{id}/what-if?at_ms=&scenario=&driver=` | Counterfactual finish (pit_now / stay_out / no_safety_car) |

**Near-live (OpenF1 polling)**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/live/sessions?year=&country=` | Sessions of a race weekend + start times |
| `POST` | `/api/live/start` | Start polling a session |
| `GET` | `/api/live/state` · `/status` · `/stream` | Current state · runner status · SSE |
| `POST` | `/api/live/stop` | Stop the runner |

## Status

- [x] Event envelope with deterministic IDs (`backend/racelens/events/`)
- [x] Replay engine: `state_at(t)`, dedupe, stable ordering (`backend/racelens/replay/`)
- [x] Determinism / dirty-data / no-future-leakage tests (`backend/tests/`)
- [x] FastF1 ingestion adapter + CLI (`ingest`, `state`) — session time rebased
      to race start, gaps/intervals derived from line-crossing times
- [x] Committed race fixtures: Monaco 2024, Spain 2024, Miami 2026 (events; regenerate positions via the pipeline)
- [x] FastAPI: 25 endpoints (state, insight, forecast, near-live)
- [x] Simulated-live stream (SSE, `/stream?speed=N`)
- [x] Insights: traffic, DRS train, pit window, undercut, tyre degradation, clean-air pace, SC pit window
- [x] Commentary renderer: EN/RU × beginner/pro templates, no AI required
- [x] OpenF1 adapter — same envelope from a second source
- [x] Near-live mode: polling runner over OpenF1, `/api/live/*`, simple live lobby (sessions + countdown)
- [x] Rust race-core resampler: raw telemetry JSONL → positions.json (500 ms ticks, linear interp, null gaps, SVG-normalised)
- [x] Real car positions in TrackMap (LIVE TELEMETRY); schematic dead-reckoning fallback
- [x] Neutralization handling: red flag / safety car / VSC detection + visualization, deterministic green-flag flash
- [x] Significant-event markers, race highlights, computed driver-of-the-day
- [x] **Forecast layer**: projected order, win probability, overtake probability, pit simulator, what-if counterfactuals
- [x] Frontend (Vite + React + TS): broadcast UI with replay/live modes, telemetry map, forecast & projection overlays
- [ ] UI/UX polish pass; live rehearsal on a real race weekend

## Disclaimer

Race Lens is an unofficial motorsport analytics project. It is not affiliated
with, endorsed by, or sponsored by Formula 1, FIA, Formula One Management, or
any team. All trademarks belong to their respective owners.
