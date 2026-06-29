# racelens.tui — terminal visualization (planned)

Headless terminal views of a race, fed by the same replay engine as the web UI.
Doubles as the live-feed monitor for the SignalR work (Phase 3): one stream,
several terminal subscribers, each rendering one layer.

## Design (lazy, pub/sub onto what already exists)

- One source of state: `ReplayEngine.state_at(atMs)` (fixture replay) or the live
  SSE stream (`/api/live/stream`).
- One command, a `--view` flag per layer. Compose by running it in several tmux
  panes — the OS does the window layout, we don't.

```
racelens tui --view table  <fixture.jsonl>   # timing tower
racelens tui --view feed   <fixture.jsonl>   # event ticker
racelens tui --view map    <fixture.jsonl>   # ASCII X/Y (later)
racelens tui --view table  --live            # subscribe to /api/live/stream
```

## Status

Stub. Build order: `--view table` on a fixture first (≈80 lines, `rich.Live`),
then `--view feed`, then `--view map`, then `--live` (SSE subscriber = Phase 3).

Dependency: `rich` (small, pure-python). No `textual` / in-window compositor —
that's the over-engineering line; separate terminals + tmux cover it.
