# Task 6 report: Textual terminal viewer

## Status

Complete. The optional `tui` extra installs Textual 8 and HTTPX 0.28, and the
`racelens-tui` entry point provides a read-only English/Russian terminal client.
It navigates the catalog, ready replays, and active production Live; renders
timing, battles, What to Watch, feed, replay timeline controls, and API-backed
track positions; and reconnects SSE with a 0.5–8 second bounded backoff.

Live lifecycle labels preserve the backend's stale, degraded, failed,
finishing, replay-ready, and ended states. Live without real XY renders an
unavailable message instead of a synthetic track. Replay tracks use Braille
when the terminal encoding supports it and ASCII otherwise.

## Focused verification

- `PYTHONPATH=backend python backend/tests/tui_check.py` — passed.
- `python -m compileall -q backend/racelens/tui.py backend/tests/tui_check.py`
  and direct `racelens.tui` import — passed.
- `racelens-tui --help` — passed; exposes `--api-url` and `--lang {en,ru}`.
- `ruff check backend/racelens/tui.py backend/tests/tui_check.py` — passed.
- `git diff --check` — passed for the task diff.

The focused check uses HTTPX's in-process mock transport and Textual's headless
runner. It covers the 100x28 boundary, catalog/replay/Live route selection,
actual track content fit, timing-table-focused seek controls, completed-replay
resume, Braille and ASCII rendering, truthful English/Russian lifecycle labels,
and bounded reconnect state. No full backend/frontend/Rust matrix was run.

## Review follow-up

- Left/right are priority bindings, so the read-only timing table cannot consume
  replay seeking when it has focus.
- A backward seek or play action before the timeline end clears the terminal
  replay state and restarts with one action.
- Track raster width and height come from the mounted widget's content region;
  the heading plus drawing fits the measured 27x12 region at exactly 100x28.
- Russian Live status now distinguishes degraded data from healthy Live and
  preserves the reconnecting suffix.

## Limitations

- The client never prepares archives or starts/stops recording; unavailable
  catalog rows remain informational because the TUI is intentionally read-only.
- ASCII fallback is automatic from the terminal encoding. Live track rendering
  remains disabled until the public Live contract supplies genuine track/XY data.
- Verification used deterministic mocked HTTP responses, not a production Live
  connection.
