# Race Lens Usefulness + Live Readiness Design

**Status:** Approved by owner on 2026-08-06

## Goal

Finish the four active product tails before building the window manager:
make tyre strategy self-explanatory, turn What to Watch into an interaction,
polish important microcopy and review-panel placement, and make race capture
start one hour early without materially growing published storage. Refresh the
README in the same pass so it describes the product that now exists.

## Constraints

- Reuse the current React components, CSS, localStorage helpers, recorder
  schedule model, and deployment scripts. Add no dependency or generic widget
  action framework.
- Battle Intelligence remains the default center view and Track remains
  optional.
- Replay stays spoiler-free. No interaction may reveal future stints, events,
  or analysis.
- Mobile retains its existing tab and Settings-drawer model.
- Use a focused check per block and one full project matrix before the final
  push/deploy.
- Preserve the untracked owner file `CV_RACE_LENS_HANDOFF.md`.

## Tyre strategy

Keep the full-race ruler because it gives strategy context, but explicitly
explain why the right side is empty early in a replay.

- Draw a vertical `NOW` marker at the current-lap percentage on every strategy
  lane, aligned with the shared ruler.
- Give the unreached portion a quiet hatched treatment labelled `FUTURE` once,
  not once per driver.
- Continue rendering only `clipStints(...)`; the future treatment is visual and
  must not contain future compounds or stint boundaries.
- Keep tooltips for every visible stint, but render inline compound/lap text
  only when the visible segment occupies enough of the full-race width to read.
- Keep loading and unavailable states unchanged.

The existing `check-stints.ts` becomes the focused check for clipping plus the
new label-visibility helper.

## What to Watch and widget actions

What to Watch is current-state guidance, not a second historical timeline.
Its useful action is therefore focus, while Highlights continues to own seek.

- Add an `onFocusDrivers(ids)` callback to `InsightPanel`.
- Render ordinary insight cards as semantic buttons. Activating one selects up
  to two unique involved drivers and opens the existing Driver Focus surface.
- Show a small `FOCUS <drivers> →` affordance so clickability is visible.
- Preserve type filters, ranking, card lifetimes, evidence, and neutralisation
  handling.
- Leave the grouped multi-driver SC pit card informational in this pass; a
  single focus target would be arbitrary.
- Timing Tower and Battle Intelligence already provide natural driver-focus
  actions, so do not build a generic action registry.

Keyboard activation and focus-visible styling are required because the card
changes from information to a control.

## Typography and review-panel placement

Raise only user-facing 9–11 px labels in the active dashboard surfaces to the
12 px floor. Decorative dots, glyphs, and geometry remain exempt. Avoid a
global scale change or per-resolution tuning.

Highlights and DOTD gain one small persisted preference:

- `ANCHOR`: current behavior below each trigger;
- `LEFT`: both review panels dock below the header from the left edge;
- `RIGHT`: both dock below the header from the right edge.

The two desktop panels receive deterministic non-overlapping offsets when
docked. At tablet/mobile widths they remain static inside Settings and ignore
the desktop docking preference. Store this preference separately from the
existing workspace presets so choosing `RACE`, `BATTLES`, or `CLEAN` does not
move review panels.

## Recorder lead time and storage

Use a hybrid capture policy:

- Race: eligible at `T−60`.
- FP1/FP2/FP3/SQ/Sprint/Q: remain eligible at `T−10`.

The extra pre-race data is written only to the recorder's local raw file.
`isolate_session()` still keeps the matching SessionInfo segment before Live
ingestion, and published event/track/position artifacts are built from the
isolated session. Tigris payload size therefore does not grow with the extra
50-minute safety window. Local raw usage grows modestly for one file per race
weekend and stays under the existing 14-day retention policy.

Expose the deployed source revision without a new service:

- pass the full Git commit to the recorder Docker build as `VCS_REF`;
- write it to `org.opencontainers.image.revision`;
- keep the existing short-SHA image tag;
- document one `docker inspect` command that prints image, revision, health,
  and read-only state.

Production proof still requires observing a future real session from scheduled
start through archive publication. This pass makes that proof attributable to
an exact build; it does not fake completion before the session exists.

## README voice

Keep the README technically credible but stop opening like formal system
documentation.

- Lead with the product experience and why it is fun: pick a race, move through
  time, and understand what the timing screen is not saying aloud.
- Use short, confident sentences with a little personality; avoid memes,
  fabricated adoption, and startup language.
- Replace the removed `ARCHIVE` button instructions with the current session
  catalog flow.
- Replace the brittle exhaustive bundled-session table with representative
  replay stories and explain that the catalog is the authoritative list.
- Preserve architecture, setup, security, recorder, API, evaluation, and legal
  details for technical readers.

## Verification

Run after each block:

- Tyres: `cd frontend && npm run check:stints`.
- What to Watch/popovers/typography: `cd frontend && npm run lint && npm run build`.
- Recorder: `cd backend && python -m pytest -q tests/test_recorder_schedule.py`.
- Documentation: `git diff --check` and direct content review.

Before the final push/deploy, run the complete backend, frontend, and Rust
matrix once. Then install the recorder build if the configured production host
is reachable and record the reported image revision. Do not claim the future
real-session proof until it actually happens.

## Out of scope

The window manager, official DOTD ingestion, Whisper retranscription, Windows
packaging, terminal UI, new Track interpolation, and demo recording remain
separate work.
