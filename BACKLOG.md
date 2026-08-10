# Race Lens product backlog

Updated: 2026-08-10

This is the active source of truth assembled from the repository Markdown,
the July audits, the August UX specification, and owner notes from chat. It is
not a new audit. Closed audit findings stay closed unless a concrete regression
is reproduced.

Status: **OPEN** needs product work, **PROOF** needs external/production
evidence, **DEFER** is intentionally waiting, and **DONE** is implemented.

## Product decisions

- Race Lens is currently a private, experimental motorsport LEGO set. Demo
  marketing and broad audience polish are not priorities until the owner wants
  to show it.
- Battle Intelligence is the default center view. Track remains an optional
  secondary view; it is not allowed to invent overtakes or look into future
  telemetry to make motion prettier.
- Do not patch every desktop resolution separately. A configurable workspace
  should ultimately absorb different screen sizes through widget minimums,
  per-widget full/compact/summary density, container queries, docking, resizing,
  hiding, and persisted layouts. Mobile may keep its dedicated tab model.
- Keep replay spoiler-free: strategy, highlights, insights, and state must not
  reveal future race information.
- Use targeted checks after each block. Run the full matrix once before a
  push/deploy/demo, not before every small edit.
- Do not start another broad system or UI audit while working this list.

## Closed foundations

- **DONE — system audit:** all 29 verified July findings were fixed. The four
  conditional items remain deployment-triggered safeguards, not current bugs.
- **DONE — UI/E2E correctness:** race-time rebasing, lap semantics, stale
  requests, Feed identity, cold-wake state, invalid sessions, focus, audio,
  reduced motion, and transcript labelling were fixed.
- **DONE — later audit code tail:** partial JSONL rows are retried; ended
  telemetry becomes null; manual Live capture appends; SC/VSC count as active;
  cold position loads are serialized; timeline event clusters were removed.
- **DONE — telemetry delivery:** the browser requests bounded position windows
  instead of downloading the full positions file initially.
- **DONE — replay navigation:** native timeline, dark styling, prominent play,
  speed controls, phase band, and spoiler-safe Highlights are implemented.
- **DONE — session selection:** opening without a replay shows an interactive
  session catalog page; the header uses the same catalog for switching.
- **DONE — current workspace direction:** Battles is default, Track is optional,
  fixed visibility presets persist, Gap Score/Win % is removed, and DOTD is
  restored as an explicitly algorithmic/local-vote feature.
- **DONE — recorder/storage foundation:** scheduled capture, restart-safe raw
  recording, verified archive triplets, private object storage, publication
  boundaries, and remote replay preparation exist.

## Open product work

| Item | Status | What is actually missing |
|---|---|---|
| Replay/feed clock alignment | **DONE** | Replay feed labels now share the timeline's lights-out origin, formation entries are labelled honestly, and raw timestamps still drive ordering and spoiler-safe cutoffs. Live keeps its session clock when no replay origin exists. |
| Tyre strategy clarity | **DONE** | The view has one continuous 1 px `NOW` boundary without ruler overflow, visible future treatment, narrow-label suppression, and truthful tooltips without leaking future stints. |
| What to Watch usefulness | **DONE** | Insight cards with drivers focus the relevant one or two cars, expose FOCUS beside the card header, and preserve type priority when insights are grouped. Safety-car summaries remain informational; broader widget usefulness stays open below. |
| Pit / What If action feedback | **DONE** | Pit-window and finish-sensitivity actions now show explicit busy/error states, reject duplicate clicks, clear superseded results, and ignore responses from an older driver, session, or replay timestamp. |
| Widget clickability | **OPEN** | The first useful-action contract is proven in What to Watch. Extend it to timing, battles, strategy, and events only where a natural action exists; decorative text must stay non-interactive. |
| Typography cleanup | **DONE** | Active statistics and controls respect the 12 px floor; the two remaining 10 px declarations are documented decorative glyphs. |
| Popup placement | **DEFER** | Review Panel ANCHOR/LEFT/RIGHT presets were removed after owner review. Highlights and DOTD are anchored to their header triggers again; any placement controls belong to the real workspace/window-manager work. |
| DOTD credibility | **OPEN** | Keep model pick and local vote clearly labelled. If a reliable official F1 fan-result source exists, show it as a separate result; never call the model result official. |
| Track motion | **DEFER** | Smoothing and terminal-tail fixes exist, but sector/telemetry updates can still create implausible relative surges at 10×. Battles-first is the current mitigation. Reopen interpolation only with an exact reproducible scene and no future-data leakage. |
| Whisper quality | **DEFER** | Machine transcripts are labelled honestly, but transcription quality itself was not improved. Re-transcribe only when radio becomes a product priority. |

## Live and operations

| Item | Status | What is actually missing |
|---|---|---|
| Capture lead time | **DONE** | Races become eligible at T−60; all other sessions remain T−10. The extra lead affects only 14-day local raw retention, not the isolated published archive. |
| Current recorder release | **PROOF** | Revision `b7a129698f81` was deployed healthy on 2026-08-06 with its exact image label verified. Observe one complete scheduled session through capture and archive publication; earlier storage smoke tests do not prove this image end to end. |
| Real Live UX | **PROOF** | Exercise the dashboard during an actual session: reconnect, quiet feed periods, SC/VSC stall reporting, radio, timing, and clean transition into the published replay. |
| Live workspace parity | **OPEN** | The future widget/workspace customization must work in Live with live-safe actions where seeking is impossible. Do this after the replay widget contract is settled. |

## Configurable workspace

| Item | Status | What is actually missing |
|---|---|---|
| Docking foundation | **OPEN, NOT FIRST** | Replace fixed presets with user-controlled show/hide, dock, resize, and narrow constraints. Persist the layout and keep a good default. |
| Movable/resizable widgets | **OPEN, LATER** | Allow useful panels to be rearranged and resized like a lightweight desktop. Start with a bounded docking grid; free-floating Windows-style behavior is a later layer. |
| Cross-screen behavior | **OPEN THROUGH WORKSPACE** | Treat screen size as available desk space rather than maintaining a long list of resolution-specific patches. Mobile may retain its dedicated tab model. |

## Experiments and packaging

- **DEFER — Windows executable:** package Race Lens as a desktop application
  only after the web workspace and Live lifecycle are stable.
- **DEFER — terminal mode:** explore a TUI replay/Live viewer and terminal-safe
  visualization as a separate playful client over the existing API.
- **DEFER — promo/demo recording:** the project is private for now. Record GIFs
  or a polished demo only when the owner wants to publish it.

## Technical debt that is not product priority

- **Replay cache:** keep `maxsize=1` for Render's 512 MB limit. When this code is
  next touched, add a short rationale comment and a two-session switching test.
  Increase it only after measuring real concurrent demand, RSS, cache misses,
  and remote-path lifetime under disk eviction.
- **Container/repository size:** about 160 MB of fixtures still sit in the
  checkout and public image. Moving all but a small fallback to the existing
  remote cache remains a valid deployment optimization, not a UX blocker.
- **Rust resampler:** do not replace it speculatively. Consider NumPy only after
  a full-session benchmark proves equal output, acceptable time, and memory.
- **Conditional safeguards:** authentication for internet-facing writable Live,
  cross-process storage locks, and extreme timestamp ceilings become work only
  if those deployment/input assumptions change.

## Documentation and housekeeping

- **DONE:** the root README now describes the current catalog, representative
  replay stories, workspace, and T−60/T−10 recorder policy.
- **DONE:** the stale remote `fix/replay-polish-followup` branch was removed;
  its tree was identical to the merged `main` result.
- **OPEN:** after this backlog is accepted, retain the two final audits only as
  history or remove them; their raw reports and completed execution plan are
  already gone.
- **OWNER FILE:** `CV_RACE_LENS_HANDOFF.md` is intentionally untracked and must
  not be edited during product work. Recheck its test counts and production
  claims before using it for a future CV revision.

## Suggested order

1. Use the next real scheduled session to prove reconnects, quiet periods,
   SC/VSC, radio, and clean replay publication on the deployed recorder release.
2. Verify remote prepared-session path lifetime against disk eviction and
   document `maxsize=1` with two-session switching behavior.
3. Add focused visibility for memory/cache misses and recorder/archive
   publication under concurrent use.
4. Extend useful click actions to the next widgets that clearly earn one.
5. Build the docking workspace around widgets that are now worth arranging;
   extend it to Live afterward.
6. Research a reliable official DOTD result source without mixing it with the
   local model or vote.
7. Whisper data work, desktop packaging, and TUI experiments when they become
   interesting again.
