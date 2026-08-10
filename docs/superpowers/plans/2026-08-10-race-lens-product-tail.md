# Race Lens Product Tail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ship resilient replay storage, real read-only production Live, trustworthy DOTD/radio, a configurable desktop workspace, and portfolio-grade terminal and Windows clients.

**Architecture:** Keep Render read-only and bridge the private recorder to the public API through bounded, expiring S3 snapshots. Preserve the existing FastAPI/React contracts where possible, add a safe lease around remote replay files, then make the stable web/API surface reusable by Textual and Tauri clients.

**Tech Stack:** Python 3.11+, FastAPI, private S3-compatible storage, React 19/Vite, react-grid-layout 2.2.4, Textual 8, HTTPX, Tauri 2/Rust.

## Global Constraints

- Public Render stays `RACELENS_READONLY=1`; public Live exposes no start/stop mutation.
- Production Live is Race-only; other sessions continue recorder/archive behavior unchanged.
- Live snapshots are spoiler-free, overwritten in place, limited to 256 KiB, emitted every 5 seconds, and stale after 20 seconds.
- Keep replay engine and positions parsed caches at `maxsize=1` for Render's 512 MB limit.
- Mobile keeps the existing tab model. Desktop workspace uses a bounded non-overlapping grid, not floating overlapping windows.
- Official F1 fan result is displayed before local vote and algorithmic pick; unavailable or ambiguous official data fails closed.
- Do not run a full local test matrix between tasks. Run one task-specific check per task; the full matrix runs once in GitHub before merge/deploy.
- Do not modify `CV_RACE_LENS_HANDOFF.md`.

---

### Task 1: Safe remote replay cache and focused diagnostics

Implement leased remote-session directories so eviction cannot delete files while an engine, positions payload, track response, timeline read, or `FileResponse` is using them. Remove the cached naked-path lifetime hazard; eviction skips active leases and re-runs after release. Keep parsed engine/positions caches at one item and document why.

Expose sanitized `GET /api/diagnostics` with revision, parsed-cache hit/miss/size, remote materialize/hit/eviction/bytes counters, disk bytes/max bytes, and coarse live source/freshness. Add `racelens recorder-status --json` reporting heartbeat age, recorder session phase, current raw file size/age, and publication state without secrets or host paths.

Acceptance: alternate and concurrently load two remote sessions under forced eviction; no stale path/404/file disappearance, no duplicate same-session cold materialization, and diagnostics contain no credentials, bucket names, or filesystem paths.

### Task 2: Private-storage production Live bridge

Add strict storage records:

- `live/current.json`: schema version, canonical session ID, replay ID, status (`live`, `finishing`, `replay_ready`, `failed`), snapshot key, timestamps, and safe failure text.
- `live/{canonical_session_id}/snapshot.json`: schema version, sequence, generated/expiry timestamps, race state, battles, active insights, recent passes, EN/RU feed, EN/RU beginner/pro commentary, radio URL/transcript, capture freshness, and data quality.

The recorder publishes only Race snapshots after the live feed identity matches the scheduled race. Reuse the existing SignalR parser/ReplayEngine; full-file reparse is acceptable until measured. Snapshot every 5 seconds only when storage is configured, queue transcripts asynchronously, publish audio immediately, set `finishing` after capture, and set `replay_ready` only after the verified archive manifest exists. A failed archive leaves a safe failed pointer and the last snapshot.

The read-only API uses local `_live` when present, otherwise a two-second process cache of remote Live. Preserve GET `/api/live/status`, `/stream`, `/feed`, `/forecast`, `/battles`, `/simulate-pit`; POST start/stop remain forbidden publicly. SSE emits end when remote status is terminal. Data quality uses raw transport growth plus snapshot freshness, not merely modeled event count.

Acceptance: a growing synthetic SignalR feed covers partial row, restart/append, quiet-but-growing transport, frozen transport, SC/VSC, radio arriving before transcript, storage read failure, and final replay transition. Snapshot over 256 KiB or invalid/stale identity is rejected.

### Task 3: Frontend production Live lifecycle

On startup, check read-only Live status. With no explicit `?session=`, enter active production Live automatically; with an explicit replay, keep it and show a `LIVE NOW` action. Preserve play-forward/no-scrub behavior. Show `REPLAY PREPARING` after finish and switch to the published replay within 10 seconds of `replay_ready`, replacing the URL without a stale old session.

Keep current local writable Live lobby behavior for development. Remote Live must expose current session name, freshness, reconnecting/stalled truth, feed/radio, WTW and battles. It must never offer public start/stop controls.

Acceptance: initial active Live, F5 reattach, SSE reconnect, stale snapshot, explicit replay during Live, finish/preparing, and replay-ready switch all render truthfully.

### Task 4: Official DOTD and measured Whisper improvement

Add a recorder/CLI importer for `https://www.formula1.com/en/results/{year}/awards/driver-of-the-day`. Extract only official vote records with exact meeting match, `votePosition=1`, driver TLA, percentage, and source URL; validate the driver exists in the replay and fail closed. Store `awards/driver-of-the-day/{replay_id}.json`; sync completed races until found and provide a one-shot 2026 backfill.

Extend Driver of the Day responses with nullable `official_result {driver, percentage, provider: "Formula 1 fan vote", source_url, fetched_at}`. Finished UI order is official result, local vote, algorithmic Race Lens pick. Before finish only provisional algorithm/local vote appears; absent official data says pending, never substitutes the algorithm.

Add a private radio evaluation CLI that consumes a gitignored JSONL manifest of 50 local clips/ground-truth transcripts and reports WER, F1 keyword accuracy, and latency for current medium-int8, prompted medium-int8 with `condition_on_previous_text=False` and tuned VAD, and distil-large-v3-int8. Accept a new default only if relative WER improves >=20%, keyword accuracy improves >=10 percentage points, and latency regression is <=25%; otherwise keep current. Persist transcript model/version metadata, never LLM-rewrite radio, and never commit audio/reference data.

Acceptance: official match/absent/malformed/wrong-event cases; UI keeps three result types distinct; evaluation output makes the pass/fail gate explicit.

### Task 5: Useful widget actions and configurable workspace

Finish only natural actions: timing selects a driver, battle selects both drivers, strategy selects its driver, replay feed seeks and focuses, Live feed focuses without seeking. Decorative text stays inert.

Replace preset-only desktop layout with `react-grid-layout` 2.2.4 and schema-v2 persisted layouts per Replay/Live. Widget IDs: timing, battles, track, insights, feed, strategy, pace, highlights, dotd. Each registry entry defines min width/height and supported `auto|full|compact|summary` density. Auto density is driven by container size. Provide show/hide, drag by header, resize, density override, reset default, and keyboard move/resize controls. Migrate the old DashboardLayout once. Remove RACE/BATTLES/CLEAN presets. Highlights/DOTD stay anchored by default but can be pinned. Disable unsupported Live widgets rather than faking data. Mobile remains tabs.

Acceptance: 1680x1050 at 100% has no overlap/clipping or active text below 12px; resize switches density; layouts persist independently; reset/migration work; 390px mobile is unchanged.

### Task 6: Textual terminal viewer

Add optional `tui` dependencies (`textual>=8,<9`, `httpx>=0.28,<1`) and `racelens-tui --api-url URL --lang en|ru`. Implement catalog, active production Live, timing, battles/WTW/feed, replay timeline and 1x/5x/10x controls. Replay track uses Unicode/Braille from existing track/position APIs with an ASCII fallback; Live without XY shows no fake track. Minimum terminal is 100x28 with a clear resize message below it.

Acceptance: catalog/replay/Live navigation, SSE reconnect, keyboard controls, language, Braille/ASCII rendering, and narrow terminal fallback.

### Task 7: Tauri Windows client

Create a Tauri 2 shell around the existing Vite frontend. Centralize API URL construction; web keeps relative `/api`, desktop defaults to `https://race-lens.onrender.com`. Permit only the production API origin and the exact Tauri origins required by FastAPI CORS. Do not embed FastAPI, recorder, Whisper, or offline fixtures.

Add a GitHub release workflow producing an unsigned Windows x64 NSIS installer on `desktop-v*` tags. Persist normal web workspace settings. Document the SmartScreen warning; defer signing, updater, ARM64, and offline backend.

Acceptance: clean Windows 11 VM installs/uninstalls, opens catalog/replay/production Live, plays radio, preserves layout, and performs no API mutation.

## Final Release Gate

Run backend Python 3.11/3.12, frontend build/lint/profile checks, Rust tests, storage/live lifecycle checks, TUI checks, and Windows packaging once in GitHub. Deploy recorder and Render only after all required checks pass. Prove the real Race lifecycle at the Dutch GP on 2026-08-23: capture at T-60, public Live p95 <=15 seconds from raw append, truthful reconnect/stall state, and automatic transition after verified replay publication.
