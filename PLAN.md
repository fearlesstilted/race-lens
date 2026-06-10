# Race Lens Plan

## 0. Working Title

**Race Lens**  
Open-source motorsport replay and intelligence engine.

Alternative product names:

- Race Lens
- Race Intel
- Sector Lens
- Apex Radar
- Pitwall Lab

Recommended current name: **Race Lens**.

Reason:

- not locked to official F1 branding;
- sounds broader than a dashboard;
- works for both fan-facing app and B2B/API framing;
- easy to explain: it is a lens over race data.

## 1. Core Idea

Most racing data tools show data tables, telemetry charts, timing gaps, or maps. Race Lens should do something more useful:

```text
raw motorsport data
-> normalized event timeline
-> deterministic race state
-> structured insights
-> replay/live UI, commentary, widgets, and API
```

The product should answer:

- what is happening now;
- why it matters;
- what changed compared to a few laps ago;
- who is gaining or losing strategically;
- what a viewer should watch next;
- how the race looked at any previous timestamp without revealing the future.

This is not just a Formula 1 dashboard. The portfolio-grade version is:

> An event-driven replay and race intelligence system that turns timing, telemetry, and session data into explainable strategy insights.

## 2. Primary Goal

The primary goal is **portfolio-grade open source**.

The secondary goal is to keep the architecture compatible with future monetization:

- hosted companion app;
- creator tool;
- media widgets;
- intelligence API;
- motorsport analytics consulting;
- later B2B if legal data sources are available.

The project should not start as a betting product or as a commercial live F1 data provider.

## 3. Why This Project Can Stand Out

Weak version:

```text
F1 timing dashboard with charts.
```

Strong version:

```text
Event-sourced race replay engine + insight layer + spoiler-free companion.
```

The differentiators:

- event-driven race model;
- deterministic replay;
- spoiler-free viewing;
- structured insight engine;
- "what to watch now" feed;
- simulated-live mode;
- Monaco Strategy Radar;
- tests against historical fixtures;
- clean public architecture;
- optional Rust module later;
- no mandatory AI/API keys.

This shows multiple senior engineering skills:

- domain modeling;
- data ingestion;
- time-series processing;
- state machines;
- event sourcing;
- WebSocket/SSE streaming;
- backend API design;
- frontend visualization;
- deterministic testing;
- data-quality handling;
- open-source packaging;
- product thinking.

## 4. Product Shape

Race Lens should be one platform with two possible surfaces.

### 4.1 Race Lens Companion

Fan-facing and creator-facing web app.

Main use cases:

- watch a race with a second-screen companion;
- replay a historical race without spoilers;
- understand strategy events;
- find key moments for content;
- inspect battles, pit windows, traffic, and tyre/stint trends.

### 4.2 Race Lens Intelligence API

Future B2B/technical surface.

Potential endpoints:

```text
/sessions
/sessions/{id}
/sessions/{id}/events
/sessions/{id}/state?timestamp=...
/sessions/{id}/insights
/sessions/{id}/battles
/sessions/{id}/traffic-risk
/sessions/{id}/pit-windows
/sessions/{id}/commentary?lang=ru&level=beginner
```

This should not be presented as "we sell F1 data". It should be:

> We turn motorsport timing streams into explainable race intelligence.

## 5. MVP Positioning

MVP name:

> Monaco Strategy Radar

MVP product statement:

> Replay-first and near-live race companion focused on Monaco-style strategy: traffic, DRS trains, pit windows, stint age, undercut risk, and spoiler-free replay.

Why Monaco:

- overtaking is hard;
- traffic matters heavily;
- track position is valuable;
- pit rejoin windows matter;
- Safety Car/VSC can change strategy;
- strategic explanations are genuinely useful.

## 6. Non-Goals For MVP

Do not build these in the first version:

- full betting product;
- official F1 branding;
- team logos;
- video streaming;
- full AI commentator;
- mandatory API keys;
- complex Rust microservice;
- gRPC;
- Kubernetes;
- native mobile app;
- strategy sandbox;
- team radio explainer;
- accurate bookmaker-grade probabilities;
- support for many racing series;
- production-grade true live system.

MVP should prove the engine and product concept, not pretend to be official infrastructure.

## 7. Data Sources

### 7.1 FastF1

Use for:

- historical session data;
- laps;
- telemetry;
- weather;
- race control messages where available;
- cache/fixtures;
- deterministic replay tests.

Important:

- great for replay and fixtures;
- not the safest foundation for polished live mode;
- should be used through an adapter layer.

### 7.2 OpenF1

Use for:

- public API access;
- sessions;
- drivers;
- laps;
- car data;
- positions;
- intervals;
- pit data;
- weather;
- possible near-live polling.

Important:

- likely best first near-live source;
- still treat as imperfect;
- build dedupe/reorder/fallback around it.

### 7.3 Jolpica

Use for:

- calendar;
- race results;
- historical metadata;
- standings-like information.

### 7.4 Future Commercial Data Feed

For B2B:

- do not depend commercially on unofficial F1 live timing;
- design the normalized event model so a legal client feed can plug in later.

## 8. Legal And Branding Position

Public project should be careful:

- no official F1 logo;
- no team logos unless licensed;
- no official F1 fonts;
- no misleading "official" wording;
- no video redistribution;
- no claim of being a licensed Formula 1 product;
- use "motorsport analytics" framing where possible;
- add disclaimer: unofficial fan-made analytics tool.

Suggested disclaimer:

```text
Race Lens is an unofficial motorsport analytics project. It is not affiliated with,
endorsed by, or sponsored by Formula 1, FIA, Formula One Management, or any team.
All trademarks belong to their respective owners.
```

## 9. Architecture

### 9.1 High-Level Flow

```text
Data adapters
  FastF1 / OpenF1 / Jolpica

-> Ingestion layer
  fetch, cache, normalize raw data

-> Event timeline
  typed normalized events

-> Race state engine
  apply events, snapshot at timestamp/lap

-> Insight engine
  traffic, DRS train, pit window, undercut, stint trends

-> Commentary renderer
  template-based EN/RU, beginner/pro

-> API and UI
  replay, simulated-live, near-live, widgets
```

### 9.2 Backend MVP

Recommended stack:

- Python 3.12;
- FastAPI;
- Pydantic v2;
- DuckDB or SQLite for MVP;
- Parquet/JSONL fixtures;
- pytest;
- Ruff;
- MyPy or Pyright if manageable;
- SSE first, WebSocket later if needed.

Why DuckDB:

- good for analytical queries;
- easy local development;
- great with Parquet;
- no heavy infrastructure for MVP.

Why SQLite might still be acceptable:

- simpler app state;
- easy to inspect;
- enough for session metadata and events.

Recommended:

- use JSONL/Parquet for event fixtures;
- use DuckDB for analytical reads;
- use SQLite only if app metadata becomes useful.

### 9.3 Rust Strategy

Do not start with a Rust microservice.

Recommended path:

Phase 1:

- Python replay engine.

Phase 1.5:

- small Rust CLI or library that processes files:

```text
input: events.jsonl
output: snapshots.jsonl / compressed_telemetry.parquet / insights.jsonl
```

Good Rust candidates:

- telemetry resampling;
- timeline compression;
- snapshot diffing;
- anomaly detection over telemetry;
- fast event replay benchmark.

Avoid in MVP:

- Rust service networking;
- gRPC;
- multi-service deployment;
- Python/Rust FFI;
- complicated shared schema generation.

### 9.4 Frontend MVP

Recommended stack:

- Vite + React + TypeScript;
- TanStack Query;
- Zustand or simple local state;
- Recharts/ECharts/uPlot for charts;
- CSS modules/Tailwind depending on preference;
- no heavy design system at first.

Main views:

- session picker;
- live/replay room;
- insights feed;
- timing table;
- battle cards;
- replay timeline;
- telemetry/lap comparison later.

## 10. Core Domain Model

### 10.1 Session

Fields:

```text
session_id
year
event_name
country
circuit
session_type
start_time
source
status
```

Examples:

```text
2024_monaco_race
2025_monaco_quali
2026_monaco_fp1
```

### 10.2 Driver

Fields:

```text
driver_id
broadcast_name
full_name
team_name
number
country
```

Do not depend on team logos in MVP.

### 10.3 Event Envelope

All events should share an envelope:

```json
{
  "event_id": "string",
  "session_id": "string",
  "type": "LapCompleted",
  "timestamp": "2026-06-07T13:24:10.123Z",
  "session_time_ms": 1234567,
  "lap": 22,
  "driver_id": "LEC",
  "source": "openf1",
  "source_seq": "optional",
  "confidence": "high",
  "payload": {}
}
```

### 10.4 Event Types MVP

Required:

```text
SessionStarted
SessionStatusChanged
LapStarted
LapCompleted
PositionChanged
GapUpdated
IntervalUpdated
PitIn
PitOut
TyreStintUpdated
RaceControlMessage
WeatherUpdated
CarTelemetrySample
DriverPositionSample
```

Insight-generated events:

```text
TrafficRiskDetected
DrsTrainDetected
PitWindowOpened
UndercutRiskChanged
CleanAirPaceUpdated
BattleDetected
StintDegradationTrendDetected
```

### 10.5 Race State

Race state at timestamp T should answer:

- current lap;
- session status;
- classification/order;
- driver gaps;
- intervals;
- tyre compound and age;
- pit count;
- last lap;
- best lap;
- sector status;
- weather snapshot;
- active battles;
- active insights;
- confidence/data-quality status.

State should be deterministic:

```text
same events + same timestamp = same state
```

## 11. Replay Model

### 11.1 Replay-First

Replay is the foundation.

Modes:

```text
historical replay
simulated live
experimental near-live
```

### 11.2 State Query

API shape:

```text
GET /sessions/{session_id}/state?at_ms=1234567
```

Returns:

```json
{
  "session_id": "2024_monaco_race",
  "at_ms": 1234567,
  "lap": 22,
  "classification": [],
  "drivers": {},
  "active_insights": [],
  "data_quality": {
    "status": "good",
    "last_event_ms": 1234500
  }
}
```

### 11.3 Simulated Live

Simulated live plays historical events at real-time or accelerated speed:

```text
events from Monaco 2024
-> emitted at 1x / 5x / 10x
-> same UI as live
```

This is crucial for:

- demos;
- tests;
- content videos;
- debugging;
- onboarding contributors.

### 11.4 Spoiler-Free Mode

Spoiler-free rule:

```text
UI can only access events and derived state <= current replay timestamp.
```

Do not show:

- final result;
- future pit stops;
- future Safety Car;
- future insights;
- post-race summary;
- timeline markers from the future.

Unlock after finish:

- full race story;
- turning points;
- final classification;
- post-race analysis.

## 12. Insight Engine

### 12.1 Philosophy

Insights should be structured data first, text second.

Bad:

```text
LLM reads raw telemetry and invents commentary.
```

Good:

```text
rule/model computes structured insight
-> renderer turns it into text
-> optional LLM polishes text later
```

### 12.2 Insight Envelope

```json
{
  "insight_id": "string",
  "session_id": "string",
  "type": "TRAFFIC_RISK_HIGH",
  "severity": "medium",
  "confidence": "high",
  "created_at_ms": 1234567,
  "expires_at_ms": 1240000,
  "lap": 22,
  "driver_ids": ["LEC", "ALO"],
  "evidence": {
    "gap": 0.8,
    "pace_loss_per_lap": 0.46,
    "track": "Monaco",
    "overtake_difficulty": "very_high"
  }
}
```

### 12.3 MVP Insights

#### Traffic Risk

Detect when a faster driver is stuck behind a slower car.

Inputs:

- interval to car ahead;
- recent lap pace;
- sector pace;
- tyre age;
- track overtake difficulty;
- DRS availability if available.

Output:

```text
TRAFFIC_RISK_LOW
TRAFFIC_RISK_MEDIUM
TRAFFIC_RISK_HIGH
```

#### DRS Train

Detect a chain of cars within roughly DRS range.

Inputs:

- intervals between adjacent cars;
- DRS activation rules/session;
- lap phase;
- number of cars in chain.

Output:

```text
DRS_TRAIN_FORMING
DRS_TRAIN_ACTIVE
DRS_TRAIN_BREAKING
```

#### Clean Air Pace

Estimate pace when not stuck in traffic.

Inputs:

- recent laps;
- gaps ahead/behind;
- tyre compound;
- stint age;
- track status;
- exclude in/out laps.

Output:

```text
CLEAN_AIR_PACE_UPDATED
```

#### Pit Window

Estimate whether a driver can pit and rejoin in a strategically useful position.

Inputs:

- estimated pit loss;
- gaps to cars behind;
- traffic after pit exit;
- tyre strategy;
- track position value.

Output:

```text
PIT_WINDOW_OPENED
PIT_WINDOW_CLOSED
PIT_REJOIN_TRAFFIC_RISK
```

#### Undercut Risk

Estimate whether a trailing driver could pit earlier and jump a rival.

Inputs:

- gap between rivals;
- pit loss;
- expected outlap pace;
- tyre delta;
- rejoin traffic;
- current traffic loss.

Output:

```text
UNDERCUT_RISK_LOW
UNDERCUT_RISK_MEDIUM
UNDERCUT_RISK_HIGH
```

#### Stint Age

Track tyre compound and age.

Inputs:

- pit stops;
- tyre data where available;
- laps since last stop.

Output:

```text
STINT_AGE_UPDATED
DEGRADATION_TREND_DETECTED
```

## 13. Commentary Renderer

### 13.1 No Mandatory AI

Default commentary should use deterministic templates.

Supported MVP dimensions:

```text
language: en, ru
level: beginner, pro
```

Example insight:

```json
{
  "type": "TRAFFIC_RISK_HIGH",
  "driver_ids": ["LEC", "ALO"],
  "evidence": {
    "gap": 0.8,
    "pace_loss_per_lap": 0.46
  }
}
```

RU beginner:

```text
Леклер теряет время за Алонсо. В Монако обгонять почти невозможно, поэтому команда может попробовать пит-стоп, чтобы вывести его из трафика.
```

EN pro:

```text
LEC is losing about 0.46s/lap behind ALO. Given Monaco's track-position value, an early stop becomes viable if the rejoin window stays clean.
```

### 13.2 Optional AI Later

Possible modes:

```text
template
local_llm
cloud_llm
```

Cloud LLM should be optional:

```text
LLM_PROVIDER=openai|groq|openrouter
LLM_API_KEY=...
```

AI should only polish commentary or generate summaries. It should not be responsible for core analytics.

## 14. UI Concept

### 14.1 Main Screen

Top bar:

```text
Race Lens | Monaco GP 2026 | Race | Lap 24/78 | LIVE
[Replay] [Sim Live] [Experimental Live]
[Spoiler-Free ON] [EN/RU] [Beginner/Pro]
```

Left panel:

```text
What To Watch Now

1. LEC stuck behind ALO
   Traffic risk: HIGH
   Losing ~0.46s/lap

2. NOR undercut window opening
   Pit window: 2-4 laps
   Rejoin traffic: medium

3. P6-P10 DRS train active
   Overtake chance: low
```

Center:

```text
Track / race map area
- driver markers
- tyre colors
- highlighted battles
- active DRS train
- optional sector status
```

Right panel:

```text
Companion Feed

Lap 24
Леклер сейчас быстрее в чистом воздухе, но теряет время за Алонсо.
В Монако это критично: если команда не освободит его через пит-стоп,
он может потерять еще несколько секунд за ближайшие круги.

Confidence: High
Evidence: gap 0.8s, pace loss 0.46s/lap
```

Bottom:

```text
Timing Table

P | Driver | Gap | Int | Tyre | Age | Last Lap | Status
1 | VER    | --  | --  | M    | 24  | 1:16.9   | stable
2 | LEC    | +3.8| 3.8 | M    | 24  | 1:17.4   | traffic
3 | NOR    | +8.1| 4.3 | H    | 6   | 1:16.7   | closing
```

Replay timeline:

```text
Lap 1 ---- Lap 18 pit window ---- Lap 31 SC ---- Lap 78
[play/pause] [0.5x] [1x] [5x] [10x]
```

In spoiler-free mode, future markers should be hidden.

### 14.2 Creator Mode Later

Potential view:

```text
Race Story

Top turning points:
1. Lap 18: undercut window opened for NOR
2. Lap 24: LEC lost time in traffic
3. Lap 31: Safety Car changed pit windows

[Export PNG]
[Export JSON]
[Copy script]
```

This is the most realistic monetization direction.

## 15. API Sketch

### 15.1 Sessions

```text
GET /api/sessions
GET /api/sessions/{session_id}
POST /api/sessions/{session_id}/ingest
```

### 15.2 Events

```text
GET /api/sessions/{session_id}/events
GET /api/sessions/{session_id}/events?until_ms=1234567
```

### 15.3 Replay

```text
GET /api/sessions/{session_id}/state?at_ms=1234567
GET /api/sessions/{session_id}/timeline
GET /api/sessions/{session_id}/stream/simulated-live
```

### 15.4 Insights

```text
GET /api/sessions/{session_id}/insights?at_ms=1234567
GET /api/sessions/{session_id}/battles?at_ms=1234567
GET /api/sessions/{session_id}/pit-windows?at_ms=1234567
GET /api/sessions/{session_id}/traffic-risk?at_ms=1234567
```

### 15.5 Commentary

```text
GET /api/sessions/{session_id}/commentary?at_ms=1234567&lang=ru&level=beginner
```

## 16. Repository Structure

Recommended first structure:

```text
race-lens/
  backend/
    app/
      main.py
      api/
      core/
      adapters/
        fastf1_adapter.py
        openf1_adapter.py
        jolpica_adapter.py
      events/
        models.py
        normalize.py
      replay/
        engine.py
        state.py
        snapshots.py
      insights/
        traffic.py
        drs_train.py
        pit_window.py
        undercut.py
        clean_air.py
      commentary/
        renderer.py
        templates/
      storage/
      tests/
        fixtures/
    pyproject.toml

  frontend/
    src/
      api/
      components/
      features/
        replay/
        insights/
        timing/
        commentary/
      pages/
      styles/
    package.json

  rust/
    race-core/
      Cargo.toml
      src/

  docs/
    architecture.md
    data-model.md
    legal-notes.md

  docker-compose.yml
  README.md
```

If starting smaller:

```text
backend/
frontend/
RACE_LENS_PLAN.md
README.md
```

Add Rust only after the Python replay path works.

## 17. Development Phases

### Phase 0: Decision And Setup

Goal:

- confirm name;
- confirm MVP scope;
- initialize repo;
- choose backend/frontend tooling.

Deliverables:

- README draft;
- repo structure;
- dev commands;
- license;
- basic CI.

### Phase 1: Historical Ingestion

Goal:

- load one historical Monaco session;
- convert useful data into normalized events.

Deliverables:

- FastF1/OpenF1 adapter;
- session metadata endpoint;
- event JSONL export;
- local cache;
- one fixture committed or downloadable.

Acceptance:

- can run one command to ingest a session;
- can inspect normalized event file;
- events have stable IDs and timestamps.

### Phase 2: Replay Engine

Goal:

- build deterministic state at timestamp T.

Deliverables:

- event applier;
- state snapshot;
- `/state?at_ms=...`;
- replay timeline;
- basic tests.

Acceptance:

- same event fixture returns same state every run;
- tests cover at least 3 timestamps;
- state includes lap, order, gaps, tyres, pits where available.

### Phase 3: Simulated Live

Goal:

- replay historical session as live stream.

Deliverables:

- SSE or WebSocket stream;
- speed control;
- frontend connection;
- live-looking UI.

Acceptance:

- Monaco historical session can play at 1x/5x/10x;
- UI updates without refresh;
- user can pause/resume.

### Phase 4: Insight Engine MVP

Goal:

- generate useful structured insights.

Deliverables:

- traffic risk;
- DRS train;
- stint age;
- pit window;
- undercut risk;
- clean air pace approximation.

Acceptance:

- active insights appear for a timestamp;
- each insight has confidence and evidence;
- no free-form AI required.

### Phase 5: Commentary Renderer

Goal:

- turn insights into understandable text.

Deliverables:

- EN beginner;
- EN pro;
- RU beginner;
- RU pro;
- templates;
- UI feed.

Acceptance:

- insight cards can switch language/level;
- text uses evidence values;
- no API keys needed.

### Phase 6: Spoiler-Free Mode

Goal:

- make replay safe for delayed viewing.

Deliverables:

- frontend spoiler-free toggle;
- backend `until_ms` filtering;
- hidden future timeline markers;
- no final result before finish.

Acceptance:

- at lap 20, API/UI cannot expose lap 21+ insights;
- post-race summary locked until race end.

### Phase 7: Experimental Near-Live

Goal:

- poll available near-live source and feed the same engine.

Deliverables:

- OpenF1 near-live adapter;
- polling;
- dedupe;
- reorder buffer;
- data quality indicator.

Acceptance:

- app can show live-ish session data;
- UI shows delay and confidence;
- reconnect/fallback does not crash app.

### Phase 8: Polish And Public Demo

Goal:

- make project presentable.

Deliverables:

- README;
- screenshots;
- demo GIF/video;
- architecture diagram;
- Docker Compose;
- GitHub Actions;
- sample session;
- known limitations.

Acceptance:

- new user can run demo locally;
- README explains value in under 30 seconds;
- project looks serious on GitHub.

## 18. Monaco Timeline Plan

Assuming about 9-10 days before Monaco weekend.

Day 1:

- initialize repo;
- create backend skeleton;
- define event models;
- ingest one historical session;
- export events.

Day 2:

- build basic replay engine;
- state at timestamp;
- first deterministic tests.

Day 3:

- frontend skeleton;
- session picker;
- timing table;
- replay controls.

Day 4:

- simulated-live stream;
- connect UI to stream;
- play/pause/speed.

Day 5:

- traffic and DRS train insights;
- insight cards in UI;
- evidence/confidence display.

Day 6:

- pit window, stint age, undercut risk;
- Monaco-specific thresholds/config.

Day 7:

- commentary renderer EN/RU beginner/pro;
- spoiler-free API filtering.

Day 8:

- OpenF1 near-live adapter;
- dirty data handling;
- data quality status.

Day 9:

- Docker;
- README;
- screenshots/demo;
- dry run on historical Monaco.

Day 10:

- Monaco FP/Quali live experiment;
- write notes from failures;
- ship public demo even if live is marked experimental.

## 19. Testing Strategy

### 19.1 Unit Tests

Test:

- event parsing;
- event ID generation;
- event ordering;
- state application;
- individual insight rules;
- commentary template rendering.

### 19.2 Golden Fixture Tests

Use fixed event files:

```text
fixtures/monaco_2024_race_events.jsonl
fixtures/monaco_2025_quali_events.jsonl
```

Test:

```text
state at 10 min
state at lap 20
state after pit stop
state after safety car
```

Expected output can be snapshot JSON.

### 19.3 Replay Determinism

Test:

```text
same events, same timestamp -> same state hash
```

### 19.4 Dirty Data Tests

Simulate:

- duplicate events;
- out-of-order events;
- missing samples;
- late update;
- reconnect gap.

Expected:

- no crash;
- dedupe works;
- data quality changes to degraded;
- state remains usable.

## 20. Data Quality Model

Every state response should include:

```json
{
  "data_quality": {
    "status": "good",
    "delay_ms": 8000,
    "last_event_at_ms": 1234567,
    "missing_sources": [],
    "warnings": []
  }
}
```

Statuses:

```text
good
delayed
degraded
stale
unknown
```

This is important for live credibility.

## 21. Monetization Hypotheses

Do not optimize MVP around monetization, but keep these paths open.

### 21.1 Creator Tool

Most realistic early monetization.

Value:

- find key race moments faster;
- generate charts/cards;
- export summaries;
- create TikTok/YouTube/LinkedIn content.

Possible paid features:

- export PNG/video cards;
- race story generator;
- branded creator templates;
- batch post-race reports;
- hosted archive.

### 21.2 Hosted Companion

Possible but uncertain.

Value:

- no setup;
- spoiler-free replay;
- personalized companion;
- saved sessions.

Risk:

- fans may not pay directly;
- data rights may limit commercial use.

### 21.3 Media Widgets

Potential B2B.

Value:

- embeddable battle cards;
- pit window radar;
- race story feed;
- localized commentary widgets.

Good first customers:

- blogs;
- newsletters;
- small sports media;
- creator websites;
- fantasy communities.

### 21.4 Betting Analytics

Possible later, not first.

Only viable if:

- client has licensed data;
- Race Lens sells analytics/explainability layer, not raw data;
- legal position is reviewed;
- SLA/latency/monitoring exist.

Public README should avoid betting positioning.

## 22. Public Content Strategy

Use the project as content engine.

TikTok/Shorts ideas:

- "Why this pit stop failed";
- "The hidden battle nobody noticed";
- "This DRS train destroyed three strategies";
- "Watching Monaco without spoilers";
- "Building an F1 race intelligence engine";
- "How race replay works under the hood";
- "Rust vs Python for telemetry processing";
- "What the timing tower does not tell you".

LinkedIn ideas:

- event-driven architecture breakdown;
- deterministic replay testing;
- dirty live data handling;
- data-source agnostic design;
- structured insights before AI;
- spoiler-free UX as product design.

GitHub README should include:

- short product GIF;
- architecture diagram;
- quick start;
- sample insight JSON;
- screenshots;
- legal disclaimer;
- roadmap;
- "Why not just a dashboard?" section.

## 23. Risks

### 23.1 Live Data Risk

Risk:

- live data can be delayed, incomplete, out of order, or unavailable.

Mitigation:

- replay-first;
- simulated-live mode;
- data quality status;
- reorder buffer;
- dedupe;
- graceful degradation.

### 23.2 Scope Risk

Risk:

- trying to build every exciting feature.

Mitigation:

- Monaco Strategy Radar only;
- no full AI;
- no betting;
- no complex Rust microservice;
- focus on replay and insights.

### 23.3 Rust Trap

Risk:

- multi-service Rust/Python bridge slows MVP.

Mitigation:

- Python engine first;
- Rust as CLI/module later;
- file-based boundary initially.

### 23.4 Legal Risk

Risk:

- official branding/data restrictions.

Mitigation:

- no logos;
- no official branding;
- unofficial disclaimer;
- data-source agnostic design;
- no commercial live data claims.

### 23.5 Product Risk

Risk:

- fans may not pay for explanations.

Mitigation:

- portfolio-first;
- creator tool angle;
- widgets/API angle;
- validate via content and public demos.

## 24. Definition Of Done For MVP

MVP is done when:

- a historical Monaco session can be ingested;
- normalized events are generated;
- replay state can be queried by timestamp;
- UI can play simulated-live replay;
- spoiler-free mode works;
- at least 4 useful insight types work;
- commentary renders in EN/RU with beginner/pro modes;
- tests prove deterministic state;
- README explains project clearly;
- demo GIF/video exists;
- Docker/local quickstart works.

Stretch:

- experimental near-live OpenF1 adapter;
- simple track map;
- Rust telemetry resampler;
- creator export cards.

## 25. First Implementation Tasks

Start tomorrow with these tasks:

1. Create repo structure.
2. Add backend FastAPI skeleton.
3. Add event models.
4. Add one ingestion command for a historical Monaco session.
5. Export normalized events to JSONL.
6. Implement basic replay state.
7. Add deterministic state tests.
8. Add frontend skeleton.
9. Show session state at selected timestamp.
10. Add simulated-live stream.

Avoid starting with:

- beautiful UI;
- Rust microservice;
- AI;
- betting;
- live SignalR;
- many languages;
- advanced telemetry charts.

## 26. One-Sentence Pitch

Short:

> Race Lens is an open-source motorsport replay and intelligence engine that turns race timing data into spoiler-free replay, strategy insights, and creator-ready explanations.

Technical:

> Race Lens normalizes motorsport data into an event timeline, deterministically reconstructs race state at any timestamp, and generates structured strategy insights for replay, live companion UIs, and analytics APIs.

Product:

> Race Lens helps fans and creators understand what actually changed in a race, not just what the timing table shows.

## 27. Current Recommendation

Build it as a portfolio-first open-source project.

Keep monetization optional:

```text
Open-source core now.
Public demos and content next.
Creator tools/widgets if people care.
B2B analytics only after traction and legal data access.
```

The strongest first public demo should be:

```text
Monaco Strategy Radar:
spoiler-free simulated-live replay with traffic, DRS train, pit window,
undercut risk, and bilingual explanation cards.
```

