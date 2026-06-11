# Race Lens

[![CI](https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml/badge.svg)](https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Open-source motorsport replay and intelligence engine.

```
raw motorsport data → normalized event timeline → deterministic race state
                    → structured insights → replay / live UI / API
```

Race Lens normalizes timing data (FastF1, OpenF1) into an immutable event timeline,
deterministically reconstructs race state at any timestamp, and generates structured
strategy insights — traffic risk, DRS trains, pit windows, undercut risk — with
human-readable commentary in English and Russian. Replay-first: the same engine
drives historical replay, simulated-live, and near-live mode. Spoiler-free by
construction: state at time `t` uses only events up to `t`.

## Demo

<!-- TODO: record 20s GIF -->

## Architecture

| Layer | What it does | Files |
|---|---|---|
| **Events** | Deterministic IDs, typed envelope, dedupe | [`racelens/events/`](backend/racelens/events/) |
| **Replay engine** | `state_at(t)`, snapshots, no future leakage | [`racelens/replay/`](backend/racelens/replay/) |
| **Insights** | 6 detectors: traffic risk, DRS train, pit window, undercut, tyre degradation, clean air pace | [`racelens/insights/`](backend/racelens/insights/) |
| **Commentary** | EN/RU × beginner/pro templates, no AI required | [`racelens/commentary/`](backend/racelens/commentary/) |
| **API / SSE** | FastAPI REST + Server-Sent Events stream + live polling | [`racelens/api.py`](backend/racelens/api.py) |
| **Adapters** | FastF1 and OpenF1 normalized to the same envelope | [`racelens/adapters/`](backend/racelens/adapters/) |

## Quickstart

**Install and test (no network needed):**

```bash
cd backend
pip install -e ".[dev,api]"
python -m pytest -q          # 71 tests, all pass
```

**Ingest a session (FastF1):**

```bash
pip install -e ".[dev,api,fastf1]"
python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
python -m racelens.cli state fixtures/monaco_2024_race.jsonl --at-ms 3600000
```

**Ingest via OpenF1 (near-live source, no extra deps):**

```bash
python -m racelens.cli ingest --source openf1 2024 Monaco R -o fixtures/monaco_2024_openf1.jsonl
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
# API at http://localhost:8000
# Fixtures mounted from ./backend/fixtures
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions` | List available sessions |
| `GET` | `/api/sessions/{id}/state?at_ms=N` | Race state snapshot at timestamp |
| `GET` | `/api/sessions/{id}/timeline` | Full event timeline |
| `GET` | `/api/sessions/{id}/insights?at_ms=N` | Structured strategy insights |
| `GET` | `/api/sessions/{id}/battles?at_ms=N` | Active wheel-to-wheel battles |
| `GET` | `/api/sessions/{id}/commentary?at_ms=N&lang=en&level=pro` | Human-readable commentary |
| `GET` | `/api/sessions/{id}/feed?until_ms=N&lang=en&limit=30` | Spoiler-free event ticker (newest first) |
| `GET` | `/api/sessions/{id}/stream?speed=N` | SSE simulated-live stream |
| `POST` | `/api/live/start` | Start near-live polling runner |
| `GET` | `/api/live/state` | Current near-live state |
| `GET` | `/api/live/status` | Runner status |
| `GET` | `/api/live/stream` | SSE near-live stream |
| `POST` | `/api/live/stop` | Stop near-live runner |

## Status

- [x] Event envelope with deterministic IDs (`backend/racelens/events/`)
- [x] Replay engine: `state_at(t)`, dedupe, stable ordering (`backend/racelens/replay/`)
- [x] Determinism / dirty-data / no-future-leakage tests (`backend/tests/`)
- [x] FastF1 ingestion adapter + CLI (`ingest`, `state`) — session time rebased
      to race start, gaps/intervals derived from line-crossing times
- [x] Real fixture: Monaco 2024 race, 4919 events (regenerate via `ingest`)
- [x] FastAPI: `/sessions`, `/state`, `/timeline`, `/insights`
- [x] Simulated-live stream (SSE, `/stream?speed=N`)
- [x] Insights: traffic risk, DRS train, pit window, undercut risk
- [x] Commentary renderer: EN/RU × beginner/pro templates, /commentary endpoint, no AI required
- [x] OpenF1 adapter — same envelope from a second source (near-live foundation)
- [x] Near-live mode: polling runner over the OpenF1 adapter, /api/live/*
- [ ] Frontend (Vite + React + TS) — in progress

## Disclaimer

Race Lens is an unofficial motorsport analytics project. It is not affiliated
with, endorsed by, or sponsored by Formula 1, FIA, Formula One Management, or
any team. All trademarks belong to their respective owners.
