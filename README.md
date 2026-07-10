---
title: Race Lens
emoji: 🏎️
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Race Lens

[![CI](https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml/badge.svg)](https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Open-source motorsport replay and race-insight engine.

```
raw motorsport data → normalized event timeline → deterministic race state
   → strategy insights + experimental pace outlook → replay / live UI / API
```

Race Lens normalizes timing data (FastF1, OpenF1) into an event timeline and
deterministically reconstructs race state at any timestamp. Its purpose is to demonstrate
a testable motorsport data pipeline, not to compete with commercial broadcast viewers.

- **Explains the present** — structured strategy insights (traffic, DRS trains, pit
  windows, undercut risk, tyre degradation, clean-air pace) with human commentary in
  English and Russian, no LLM required.
- **Explores scenarios** — an explicitly uncalibrated pace outlook, gap-pressure and
  attack scores, a pit-stop estimate, and strategy sensitivity controls. These are
  transparent heuristics, not probabilities or betting-grade predictions.

Replay-first: the same engine drives historical replay, simulated-live, and optional local
near-live capture. Timestamp-scoped state, feed, and insight paths use only events up to
time `t`; full-race markers and highlights are opt-in and the UI starts spoiler-free.
Plain explainable rules throughout; no machine learning.

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
| **Experimental outlook** | Pace ordering, gap/attack scores, pit estimate, strategy sensitivity — deterministic, uncalibrated | [`racelens/forecast/`](backend/racelens/forecast/) |
| **Significant events** | Crashes, penalties, lead changes, flags → timeline markers, highlights, driver-of-the-day | [`racelens/events_significant.py`](backend/racelens/events_significant.py) |
| **Commentary** | EN/RU × beginner/pro templates, no AI required | [`racelens/commentary/`](backend/racelens/commentary/) |
| **API / SSE** | FastAPI REST + Server-Sent Events stream + live polling | [`racelens/api.py`](backend/racelens/api.py) |
| **Adapters** | FastF1 and OpenF1 normalized to the same envelope | [`racelens/adapters/`](backend/racelens/adapters/) |
| **race-core** | Rust CLI resampler: raw JSONL → positions.json (500 ms ticks, linear interp, normalised to SVG viewbox) | [`rust/race-core/`](rust/race-core/) |
| **Frontend** | React + TS broadcast UI: timing tower, telemetry track map, insight feed, pace and strategy overlays | [`frontend/src/`](frontend/src/) |

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
python -m pytest -q
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

The single-container `Dockerfile` defaults to `RACELENS_READONLY=1`: public demos can
replay committed fixtures but cannot start capture processes or download/write sessions.
Local `docker compose` explicitly enables writable live tooling.

## Validation

Run the committed walk-forward scoreboard from `backend`:

```bash
PYTHONPATH=. python scripts/evaluate_forecast.py
```

Current four-fixture result (243 lap checkpoints):

| Metric | Current-order baseline | Pace outlook |
|---|---:|---:|
| Final-order MAE (positions) | **1.20** | 1.41 |
| Eventual winner ranked first | **200 / 243** | 197 / 243 |

The normalized gap-pressure score has a multiclass Brier score of `0.663`; it is not
calibrated and is therefore labelled a score in the UI. The replay invariant check reports
`0 / 243` checkpoints where the classified leader has a non-zero or missing gap. The pace
outlook currently loses to the naive baseline, so it remains an experiment rather than a
product claim.

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
| `GET` | `/api/sessions/{id}/markers?until_ms=N` | Significant-event timeline markers, optionally cutoff |
| `GET` | `/api/sessions/{id}/highlights?top_n=N&until_ms=N` | Highlights up to an optional cutoff |
| `GET` | `/api/sessions/{id}/driver-of-day` | Computed driver-of-the-day + candidates |

**Experimental analysis**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions/{id}/forecast?at_ms=&laps=` | Uncalibrated short-horizon pace outlook |
| `GET` | `/api/sessions/{id}/win-prob?at_ms=N` | Normalized gap-pressure score (legacy path name) |
| `GET` | `/api/sessions/{id}/win-prob-series?until_ms=&samples=` | Gap-pressure score over time |
| `GET` | `/api/sessions/{id}/overtake?at_ms=&ahead=&behind=` | Attack score for an adjacent pair |
| `GET` | `/api/sessions/{id}/simulate-pit?at_ms=&driver=` | Approximate rejoin and undercut estimate |
| `GET` | `/api/sessions/{id}/what-if?at_ms=&scenario=&driver=` | Strategy sensitivity (`pit_now` / `stay_out`) |

**Optional local near-live capture**

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
- [x] Recorded telemetry positions in replay TrackMap; schematic dead-reckoning fallback in live mode
- [x] Neutralization handling: red flag / safety car / VSC detection + visualization, deterministic green-flag flash
- [x] Significant-event markers, race highlights, computed driver-of-the-day
- [x] **Experimental analysis layer**: pace outlook, gap/attack scores, pit estimate, strategy sensitivity
- [x] Frontend (Vite + React + TS): broadcast UI with replay/live modes, telemetry map, analysis overlays
- [ ] Calibrate or remove the pace outlook after broader race-by-race evaluation

## Disclaimer

Race Lens is an unofficial motorsport analytics project. It is not affiliated
with, endorsed by, or sponsored by Formula 1, FIA, Formula One Management, or
any team. All trademarks belong to their respective owners. This repository is
intended as a personal engineering portfolio and research demo; users are responsible
for complying with the terms and redistribution rules of their chosen data sources.
