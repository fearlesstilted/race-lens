# Race Lens UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan task-by-task with spec and code-quality review.

**Goal:** Turn the current audit-driven dashboard into a calmer, readable replay workspace that exposes the useful controls, removes misleading features, and never reveals future strategy during playback.

**Architecture:** Keep the existing React dashboard, Session Catalog, persisted dashboard layout, and API contracts. Simplify presentation in place: one session trigger, one visible center-view switch, one native replay slider, and fewer analytics. The only new reusable logic is a tiny pure tyre-stint clipping function with one runnable assertion script.

**Tech Stack:** React 19, TypeScript 5.9, native HTML controls, CSS, Vite, Node assertion scripts.

## Global constraints

- Preserve the untracked user file `CV_RACE_LENS_HANDOFF.md`.
- Add no dependencies, design systems, state stores, or window-manager abstractions.
- Do not change backend or fixture data in this pass.
- Keep the existing Settings drawer accessibility behavior: focus entry, focus containment, Escape, and focus return.
- Keep future events hidden during replay. Highlights may expose only events at or before the current replay time.
- Use Barlow Condensed for compact UI/data labels and Inter for sentence copy; eliminate user-facing text below 12px.
- Each implementation task owns the files listed under it. Workers must not revert concurrent edits.

---

## Task 1: Header, session entry, and quiet supporting copy

**Owner:** header/archive worker

**Files:**

- Modify: `frontend/src/features/replay/TopBar.tsx`
- Modify: `frontend/src/features/replay/TimingTower.tsx`
- Modify: `frontend/src/features/replay/SessionCatalog.tsx`
- Modify: `frontend/src/features/replay/InsightPanel.tsx`
- Modify: `frontend/src/style.css`

### Steps

- [ ] Replace the three replay `<select>` elements and separate `ARCHIVE` button with one button labelled `YEAR · EVENT · SESSION`; clicking it calls the existing `onCatalogOpen` callback.
- [ ] Remove the replay/source metadata line and top-bar language controls. Keep mode controls, Layers, Highlights, and Settings; show Live only through the existing availability state.
- [ ] Remove DOTD imports and rendering from `TopBar`. Do not add a replacement.
- [ ] Keep session selection inside the existing `SessionCatalog`; remove its worker/source notice and implementation-style kicker.
- [ ] Increase archive round labels to at least 12px and Grand Prix names to about 20px while preserving keyboard/button semantics.
- [ ] Increase Timing Tower labels and values to the approved scale and delete every rendered `No data` placeholder; an absent value should leave a quiet blank or omit its secondary row.
- [ ] Increase What to Watch sentence/chip text and remove an empty `INFO` badge rather than filling it with invented content.
- [ ] Run `cd frontend && npm run lint`. Expected: exit 0 with no new ESLint errors.
- [ ] Run `cd frontend && npm run build`. Expected: TypeScript and Vite build successfully.
- [ ] Commit only owned files: `git commit -m "polish replay header and supporting copy"`.

## Task 2: Battle intelligence and spoiler-safe tyre strategy

**Owner:** analytics/strategy worker

**Files:**

- Create: `frontend/src/lib/stints.ts`
- Create: `frontend/scripts/check-stints.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/features/replay/BattleIntelligence.tsx`
- Modify: `frontend/src/features/replay/StintTimeline.tsx`
- Modify: `frontend/src/styles/features.css`

### Steps

- [ ] Write `check-stints.ts` first. Assert that at replay lap 13, a lap 1–10 stint remains whole, a lap 11–20 stint is clipped to 11–13 with `laps: 3`, and a lap 21–30 stint is omitted. Run it and confirm it fails because `clipStints` does not exist.
- [ ] Add the minimal pure `clipStints(stints, currentLap)` implementation in `src/lib/stints.ts`. Preserve input order, omit future stints, and return a copied last visible stint with a clipped `end_lap` and recomputed inclusive `laps`.
- [ ] Add `check:stints` to `package.json`, run `cd frontend && npm run check:stints`, and confirm the assertion script passes.
- [ ] Give `StintTimeline` a required `currentLap` prop, render explicit loading and unavailable states, and render only `clipStints(...)` output. Keep segment position/width relative to the full race so the blank right side visibly means "not happened yet".
- [ ] Add a compact compound legend, a lap ruler, taller bars, and labels containing compound plus visible lap range. Keep the existing compound colors and API call.
- [ ] Simplify Battle Intelligence to `SESSION READY / FORMATION LAP`, `TOP 3`, `RACE`, `ACTIVE BATTLES`, and `5-LAP PACE`. Delete implementation kickers, instruction paragraphs, duplicated status labels, `0 GROUPS`, and `LOWER IS BETTER`.
- [ ] Replace normalized pace bars with readable ordered rows showing driver, average lap time, and delta to the fastest visible driver. Do not invent a new score.
- [ ] Delete obsolete DOTD, Gap Score, marker, and retired battle-decoration CSS rules from `features.css` after their callers are removed; leave unrelated track/overlay rules intact.
- [ ] Run `cd frontend && npm run check:stints && npm run lint && npm run build`. Expected: all exit 0.
- [ ] Commit only owned files: `git commit -m "simplify race analytics and tyre strategy"`.

## Task 3: Visible workspace switch and native replay controls

**Owner:** shell/timeline worker

**Files:**

- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/features/replay/SettingsDrawer.tsx`
- Modify: `frontend/src/features/replay/ReplayDeck.tsx`
- Modify: `frontend/src/features/replay/replayTypes.ts`
- Modify: `frontend/src/styles/dashboard.css`
- Modify: `frontend/src/styles/responsive.css`
- Delete: `frontend/src/features/replay/DriverOfDayPanel.tsx`
- Delete: `frontend/src/features/replay/WinProbGraph.tsx`

### Steps

- [ ] Remove the `winProb`/Gap Score state, Settings toggle, center tab, graph render path, and component file. Remove DOTD from the Settings drawer and delete its component file.
- [ ] Add a visible `BATTLES | TRACK` segmented switch next to the center-panel heading, backed directly by the existing persisted `dashboardLayout.center` value. Do not add new state or storage.
- [ ] On mobile, label the center tab with the active view (`BATTLES` or `TRACK`) instead of `RACE`; preserve the existing timing/insights/feed tabs and 44px touch targets.
- [ ] Pass the current replay lap into `StintTimeline` for spoiler-safe clipping.
- [ ] Replace the custom clickable `role="slider"` rail, marker clusters, marker glyphs, marker click handlers, and spoiler toggle with one native `<input type="range">`. Use `min=start_ms`, `max=end_ms`, the current replay time as `value`, and `onChange` to call `onScrub`.
- [ ] Keep the status phase band, but always neutralize its future portion from the current cursor onward. Keep `aria-label` and a readable value announcement without recreating native keyboard handling.
- [ ] Make play/pause an icon-only centered button with a truthful `aria-label`; keep the speed buttons as a compact semantic group.
- [ ] Delete CSS for removed marker glyphs, cursor pill duplication, Gap Score, DOTD, and obsolete controls. Style the native range with CSS only and retain a clear focus indicator.
- [ ] Run `cd frontend && npm run check:ui`. Expected: the script passes after removing obsolete timeline-marker assertions and imports from the existing check script if they no longer describe product behavior.
- [ ] Run `cd frontend && npm run lint && npm run build`. Expected: all exit 0.
- [ ] Commit only owned files plus the minimal `check-broadcast-overlay.ts` cleanup: `git commit -m "simplify replay navigation and workspace views"`.

## Task 4: Integrate concurrent work and remove dead seams

**Owner:** primary agent

**Files:**

- Modify only the smallest set of files needed to resolve interface conflicts from Tasks 1–3.

### Steps

- [ ] Rebase the three owned changes in the shared worktree mentally: inspect `git diff main...HEAD`, resolve prop mismatches without restoring deleted features, and ensure `StintTimeline` receives `currentLap` exactly once.
- [ ] Run `rg -n "DriverOfDay|DOTD|WinProb|winProb|GAP SCORE|rail-marker|No data|source:" frontend/src frontend/scripts`. Expected: no user-facing or dead-code matches; any legitimate API type match must be documented rather than deleted.
- [ ] Run `rg -n "font-size:\s*(7|8|9|10|11)px" frontend/src`. Expected: no user-facing microcopy declarations remain; decorative-only exceptions require an inline reason.
- [ ] Run `cd frontend && npm run check:ui && npm run check:track && npm run check:stints && npm run lint && npm run build`. Expected: all exit 0.
- [ ] Commit integration-only fixes: `git commit -m "integrate UX polish pass"`. Skip this commit if there are no integration changes.

## Task 5: User-view verification against the approved design

**Owner:** primary agent

**Files:**

- Modify only defects directly observed during verification.

### Steps

- [ ] Start the existing local backend and frontend. Do not install tools or add a browser-test framework.
- [ ] At desktop width, verify: one session trigger opens Catalog; no DOTD or Gap Score; BATTLES/TRACK is obvious; Timing and What to Watch are readable; Battle cards contain only approved facts; pace is a ranked table; tyre strategy reveals only laps already run; timeline has no event forest; play/pause and speed remain obvious.
- [ ] At 390px width, verify: no horizontal page overflow; the active center tab is named correctly; controls do not overlap; interactive targets are at least 44px where they are primary touch actions; Settings focus containment, Escape, and focus return still work.
- [ ] Scrub Hungary from formation through lap 13 and verify strategy grows forward without revealing future stints. Switch to Belgium and Bahrain through Catalog and verify the session trigger and dashboard update cleanly.
- [ ] Verify future phase changes and Highlights are not exposed before the replay cursor.
- [ ] Compare the implementation against all 20 approved screenshot notes and the design spec; fix only concrete misses.
- [ ] Re-run the Task 4 targeted matrix after any fix. Expected: all commands exit 0.
- [ ] Run `git status --short`; confirm `CV_RACE_LENS_HANDOFF.md` is still untracked and untouched, and only intentional UX files are staged/committed.
- [ ] Commit any observed visual fixes: `git commit -m "finish UX polish verification"`. Skip if no files changed.

## Completion gate

- [ ] Use `superpowers:verification-before-completion` and report command evidence, not memory.
- [ ] Use `superpowers:requesting-code-review` for a focused code review of this branch; address only reproducible correctness, accessibility, spoiler, or regression findings.
- [ ] Do not merge, push, deploy, or record a demo until the full project test matrix is run after this UX tail and the separate system tail are both closed.
