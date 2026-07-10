# Race Lens — invariants and commands

Motorsport replay + prediction engine. Backend Python (FastAPI) in `backend/`,
frontend React+TS (vite) in `frontend/`.

## Invariants (do not break)

- `Event` (backend/racelens/events/models.py) is the single contract between
  adapters and everything else. `event_id` = deterministic sha1 of content —
  dedup, source interchangeability and re-parse idempotency all depend on it.
- `ReplayEngine.state_at(t)` uses only events with `session_time_ms <= t`.
  Spoiler-free UI, agent-loop safety and ML no-leakage all hang on this.
- Live rebuilds the engine from scratch every poll (`runner.py`) — rebuild,
  never mutate. O(n) per poll is a paid-for price, don't "optimize" it away.
- Core `racelens/` depends only on `pydantic`. `fastf1` is an optional extra,
  imported lazily; live parsing uses our own `adapters/f1live_adapter.py`
  (fastf1's live path drops keyframes — dead end, don't go back).
- Forecast constants (pit loss, tyre advantage…) are hand-tuned; treat as
  calibration targets, not truths. `README` promises explainable models —
  ML goes in as a *challenger* on a scoreboard, never a silent replacement.

## Gates (run before any commit)

- `cd backend && python3 -m pytest -q && ruff check racelens/`
- `cd frontend && npx tsc -b && npm run build && npm run lint`
  (2 known HighlightsPanel warnings are OK)

## Git

- Commit as the user, no Claude co-author trailer. Push to origin explicitly.

## Layer map

adapters (fastf1 | openf1 | f1live | jsonl) → Event → ReplayEngine.state_at(t)
→ insights/ (registry.py) + forecast/ + commentary/ + positions/ → api.py
(REST + SSE). api.py knows everyone; nobody knows api.py.

## Ops

- Servers: `uvicorn racelens.api:app --port 8000` + `npm run dev` (vite :5173).
  Live-mode diagnosis: DEBUGGING.md. Deploy: Dockerfile (single container).
- `ponytail:` comments in code = deliberate shortcuts with named ceilings.
- Plans live in `~/.claude/plans/`; session context in Claude memory.
