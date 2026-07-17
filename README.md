<h1 align="center">🏎️ RACE LENS</h1>

<p align="center"><strong>Deterministic motorsport replay and race analysis.</strong></p>

<p align="center">
  <a href="https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml"><img src="https://github.com/fearlesstilted/race-lens/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
</p>

<p align="center"><strong><a href="https://race-lens.onrender.com">Open the live demo</a></strong></p>

Race Lens turns recorded timing events into an explainable race state at any
point in time. The same event timeline always produces the same replay, which
makes the system straightforward to inspect, test, and extend.

```text
recorded event fixtures
       ↓
normalized event timeline
       ↓
deterministic replay engine
       ↓
REST + SSE → React broadcast UI
       ↓
insights, commentary, highlights, and experimental strategy tools
```

This is a personal engineering portfolio project, not a commercial timing
product. It focuses on data normalization, replay correctness, transparent
heuristics, and a polished end-to-end demo.

## Try the demo

Open [race-lens.onrender.com](https://race-lens.onrender.com). The free instance
may take up to a minute to wake after inactivity.

To run it locally:

```bash
docker compose up --build
```

Then open:

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs

Start with **Bahrain 2021** for the historical strategy duel, or **Spain 2024**
for the densest 500 ms telemetry. Every bundled race includes recorded
positions, so the track map works without FastF1, Rust, or preprocessing.

The root `Dockerfile` builds a single public-demo image on port `7860`.
It runs as a non-root user with `RACELENS_READONLY=1`, so public deployments
can replay committed data but cannot start capture jobs or write fixtures.

## What it demonstrates

- A typed event envelope shared by replay fixtures and optional data adapters.
- Stable event IDs, deterministic ordering, deduplication, and snapshots.
- Timestamp-scoped replay with no future-data leakage.
- FastAPI REST endpoints and Server-Sent Events for replay and near-live modes.
- Rule-based race insights and deterministic EN/RU commentary.
- A React + TypeScript broadcast UI with timing, track, feed, and strategy views.
- A small Rust telemetry resampler for uniform 500 ms position frames.
- Honest evaluation: experimental pace models are compared with a naive baseline.

## Architecture

| Layer | Responsibility | Code |
|---|---|---|
| Events | Typed envelope, stable IDs, JSONL loading | [backend/racelens/events/](backend/racelens/events/) |
| Replay | `state_at(t)`, snapshots, ordering, dedupe | [backend/racelens/replay/](backend/racelens/replay/) |
| Adapters | Optional FastF1, OpenF1, and F1 live normalization | [backend/racelens/adapters/](backend/racelens/adapters/) |
| Insights | Traffic, DRS trains, pit windows, undercut, degradation, clean air, safety car | [backend/racelens/insights/](backend/racelens/insights/) |
| Analysis | Pace outlook, pressure scores, pit and what-if estimates | [backend/racelens/forecast/](backend/racelens/forecast/) |
| Narrative | Commentary, significant events, highlights, driver of the day | [backend/racelens/commentary/](backend/racelens/commentary/) |
| API | FastAPI REST, SSE, and local near-live runner | [backend/racelens/api.py](backend/racelens/api.py) |
| Telemetry | Rust JSONL-to-position-frame resampler | [rust/race-core/](rust/race-core/) |
| Recorder | Scheduled capture, archive validation, radio merge, and CI-gated publication | [backend/racelens/recorder/](backend/racelens/recorder/) |
| UI | React + TypeScript replay/live dashboard | [frontend/src/](frontend/src/) |

## Bundled data

| Session | Replay story | Recorded positions |
|---|---|:---:|
| Bahrain 2021 race | Hamilton–Verstappen strategy duel | yes |
| Germany 2019 race | Wet-weather chaos and repeated safety cars | yes |
| São Paulo 2021 race | Hamilton recovery drive and overtaking | yes |
| Monaco 2024 race | Street-circuit traffic and strategy | yes |
| Spain 2024 race | High-density reference replay | yes |
| Miami 2026 race | Current-era archive replay | yes |
| Silverstone 2026 race | Deterministic fixture replay | yes |

Silverstone uses recorded XY for the map but fixture events for tower ordering,
because its archived lap-progress channel is incomplete.

Spa 2026 FP1, qualifying, and race track metadata is also included for the
near-live track view. Large raw telemetry and most derived position files stay
out of Git.

The historical set stays within FastF1's full-telemetry era (2018 onward). The
event fixtures power the demo and golden tests; they are snapshots, not a claim
of live accuracy or permission to redistribute upstream data elsewhere.

## Run from source

### Backend

```bash
cd backend
pip install -e ".[dev,api]"
uvicorn racelens.api:app --reload
```

Useful checks:

```bash
python -m pytest -q
ruff check racelens/ scripts/ tests/
```

FastF1 is optional. It powers historical ingestion and track/position telemetry;
the recorded demo does not need it:

```bash
pip install -e ".[dev,api,fastf1]"
python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
```

OpenF1 is the archive-download and polling source. It uses the base API
dependencies and is not needed to replay committed sessions:

```bash
python -m racelens.cli ingest-openf1 2024 Monaco -o fixtures/monaco_2024_openf1.jsonl
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

The browser reads replay state from the FastAPI API. During development, Vite
proxies `/api` to `http://localhost:8000`; set `RACELENS_API_TARGET` to
override it.

Useful checks:

```bash
npm run build
npm run lint
```

### Position telemetry

```bash
cd backend
python -m racelens.cli track 2024 Monaco R \
  -o fixtures/monaco_2024_race.track.json
python -m racelens.cli positions-raw 2024 Monaco R \
  -o fixtures/monaco_2024_race.positions_raw.jsonl

cd ../rust/race-core
cargo run --release -- \
  ../../backend/fixtures/monaco_2024_race.positions_raw.jsonl \
  ../../backend/fixtures/monaco_2024_race.track.json \
  ../../backend/fixtures/monaco_2024_race.positions.json \
  500
```

The Rust CLI linearly interpolates short gaps, emits null frames across longer
gaps, and normalizes raw coordinates to the SVG viewbox.

### Unattended race weekends

The optional Debian recorder follows the FastF1 UTC schedule from FP1 through
the race. It starts early, records the F1 SignalR feed, verifies the meeting,
round, year, and session before accepting data, and resumes safely after a
restart. Raw and provisional data stay on the server; archive processing is
retried without repeating capture.

Races and sprints pass an archive coverage gate before a three-file fixture is
sent through an isolated `capture/*` branch. GitHub Actions runs Python, Rust,
frontend, and fixture validation before moving `main`, which in turn lets
Render deploy the already-checked commit. See
[deploy/recorder/README.md](deploy/recorder/README.md) for deployment details.

## API guide

FastAPI exposes the complete interactive contract at `/docs`. The main route
groups are:

| Area | Routes |
|---|---|
| Discovery | `GET /api/ping`, `/api/capabilities`, `/api/sessions` |
| Replay | `/api/sessions/{id}/state`, `/api/sessions/{id}/stream`, `/timeline`, `/track`, `/positions` |
| Race story | `/api/sessions/{id}/insights`, `/battles`, `/commentary`, `/feed`, `/markers`, `/highlights`, `/driver-of-day` |
| Experimental | `/api/sessions/{id}/forecast`, `/win-prob`, `/overtake`, `/simulate-pit`, `/what-if` |
| Local near-live | `/api/live/sessions`, `POST /api/live/start`, `/api/live/status`, `/api/live/stream`, `/api/live/feed`, `POST /api/live/stop` |

Replay endpoints accept timestamps such as `at_ms` or `until_ms`. State,
insights, and feed responses only use events available up to that cutoff.
Full-race markers and highlights are explicit requests, which keeps the UI
spoiler-free by default.

## Evaluation and limits

The forecast layer is deliberately presented as experimental. Run its
walk-forward scoreboard from `backend`:

```bash
PYTHONPATH=. python scripts/evaluate_forecast.py
```

On the committed four-race evaluation set (243 lap checkpoints), the current
pace outlook has a final-order MAE of `1.41` positions versus `1.20` for the
current-order baseline. The baseline also ranks the eventual winner first at
`200/243` checkpoints versus `197/243` for the outlook.

That result is intentionally visible: the model is an explainable experiment,
not a probability, betting signal, or production prediction claim. Forecast
constants are hand-tuned and need broader calibration before stronger use.

## Disclaimer

Race Lens is an unofficial motorsport analytics project. It is not affiliated
with or endorsed by Formula 1, FIA, Formula One Management, or any team. All
trademarks belong to their respective owners. Users are responsible for the
terms and redistribution rules of their chosen data sources.

Released under the [MIT License](LICENSE).
