# Race Lens

Open-source motorsport replay and intelligence engine — work in progress.

```
raw motorsport data → normalized event timeline → deterministic race state
                    → structured insights → replay / live UI / API
```

Race Lens normalizes timing data (FastF1, OpenF1) into an event timeline,
deterministically reconstructs race state at any timestamp, and will generate
structured strategy insights: traffic risk, DRS trains, pit windows, undercut
risk. Replay-first: the same engine drives historical replay, simulated-live
and (later) near-live mode. Spoiler-free by construction — state at time `t`
is built only from events up to `t`.

Full design: [PLAN.md](PLAN.md).

## Status

- [x] Event envelope with deterministic IDs (`backend/racelens/events/`)
- [x] Replay engine: `state_at(t)`, dedupe, stable ordering (`backend/racelens/replay/`)
- [x] Determinism / dirty-data / no-future-leakage tests (`backend/tests/`)
- [x] FastF1 ingestion adapter + CLI (`ingest`, `state`)
- [ ] Fixture: real Monaco race ingested and committed
- [ ] FastAPI: `/sessions/{id}/state?at_ms=...`
- [ ] Simulated-live stream (SSE)
- [ ] Insight engine MVP
- [ ] Frontend (Vite + React + TS)

## Quickstart

```bash
cd backend
pip install -e ".[dev]"
pytest                       # replay engine tests, no network needed

pip install -e ".[fastf1]"
python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
python -m racelens.cli state fixtures/monaco_2024_race.jsonl --at-ms 3600000
```

## Disclaimer

Race Lens is an unofficial motorsport analytics project. It is not affiliated
with, endorsed by, or sponsored by Formula 1, FIA, Formula One Management, or
any team. All trademarks belong to their respective owners.
