# Race Lens Usefulness + Live Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current replay widgets worth using, make race capture safer at T−60, refresh the public README, and ship the result.

**Architecture:** Extend the existing components and persisted preferences in place. What to Watch reuses Driver Focus, tyre strategy reuses the spoiler-safe clipped data, review panels gain one small independent dock preference, and recorder scheduling keeps its pure `ScheduledSession` boundary.

**Tech Stack:** React 19, TypeScript 5.9, CSS, Python 3.11/3.12, pytest, Docker, GitHub Actions, Render.

## Global Constraints

- Add no dependency, state store, generic widget action registry, or window-manager abstraction.
- Preserve spoiler-free replay behavior and the Battles-first workspace.
- Keep mobile tabs and static Settings-drawer review panels unchanged.
- Preserve `CV_RACE_LENS_HANDOFF.md` untracked and untouched.
- Run focused checks after each block and the full matrix once before push/deploy.

---

### Task 1: Explain the tyre-strategy future

**Files:**
- Modify: `frontend/src/lib/stints.ts`
- Modify: `frontend/scripts/check-stints.ts`
- Modify: `frontend/src/features/replay/StintTimeline.tsx`
- Modify: `frontend/src/styles/features.css`

**Interfaces:**
- Consumes: `clipStints(stints, currentLap)` and the existing `currentLap`/`total_laps` values.
- Produces: `showStintLabel(laps, totalLaps): boolean`, a `NOW` marker, and one visual-only future region.

- [ ] **Step 1: Extend the focused check first**

Add assertions to `check-stints.ts` proving that one-lap and four-percent segments hide inline text while an eight-percent segment shows it. Import `showStintLabel` from `src/lib/stints.ts`.

- [ ] **Step 2: Run the check and observe the missing export**

Run: `cd frontend && npm run check:stints`

Expected: failure because `showStintLabel` does not exist.

- [ ] **Step 3: Add the minimal pure helper**

Implement:

```ts
export function showStintLabel(laps: number, totalLaps: number): boolean {
  return totalLaps > 0 && laps / totalLaps >= 0.08
}
```

- [ ] **Step 4: Render progress without future data**

In `StintTimeline`, clamp current progress to `0..100`, render one `FUTURE` overlay and one `NOW` line inside each shared-width bar/ruler area, and use `showStintLabel` to omit unreadable inline labels. Keep every visible stint tooltip.

- [ ] **Step 5: Style the explanation**

Add a quiet diagonal future hatch, red `NOW` hairline/label, and avoid pointer interception. Do not render future compound colors or boundaries.

- [ ] **Step 6: Run the focused check**

Run: `cd frontend && npm run check:stints`

Expected: `stint clipping check passed` with exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/stints.ts frontend/scripts/check-stints.ts frontend/src/features/replay/StintTimeline.tsx frontend/src/styles/features.css
git commit -m "polish tyre strategy progress"
```

### Task 2: Make What to Watch open Driver Focus

**Files:**
- Create: `frontend/src/lib/insightFocus.ts`
- Create: `frontend/scripts/check-insight-focus.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/features/replay/InsightPanel.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles/dashboard.css`

**Interfaces:**
- Produces: `focusDriverIds(ids: string[]): string[]`, returning the first two unique, non-empty driver IDs.
- `InsightPanel` gains `onFocusDrivers?: (ids: string[]) => void`.

- [ ] **Step 1: Write the focused assertion script**

Assert that `['NOR', 'VER', 'NOR', 'LEC']` becomes `['NOR', 'VER']` and empty values are discarded. Add `check:insight-focus` to `package.json`.

- [ ] **Step 2: Run it and observe the missing helper**

Run: `cd frontend && npm run check:insight-focus`

Expected: failure because `src/lib/insightFocus.ts` does not exist.

- [ ] **Step 3: Implement the helper**

Use one loop and a `Set`; stop after two IDs. No generic action type.

- [ ] **Step 4: Turn ordinary insight cards into controls**

Render `InsightCard` as a button only when it has focusable drivers and the callback exists. Add `FOCUS <ids> →`, preserve all evidence/copy, and leave the grouped SC pit card informational.

- [ ] **Step 5: Wire atomic focus in `main.tsx`**

Set `selectedIds` directly from `focusDriverIds`, rather than replaying the row-toggle handler. Pass it to `InsightPanel` in replay and Live.

- [ ] **Step 6: Add control states**

Reset button chrome, keep the current card visuals, and add hover plus `:focus-visible` treatment.

- [ ] **Step 7: Run the focused check and frontend static checks**

Run: `cd frontend && npm run check:insight-focus && npm run lint && npm run build`

Expected: all exit 0.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/scripts/check-insight-focus.ts frontend/src/lib/insightFocus.ts frontend/src/features/replay/InsightPanel.tsx frontend/src/main.tsx frontend/src/styles/dashboard.css
git commit -m "make race insights actionable"
```

### Task 3: Polish important type and dock review panels

**Files:**
- Create: `frontend/scripts/check-review-dock.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/features/replay/replayTypes.ts`
- Modify: `frontend/src/features/replay/TopBar.tsx`
- Modify: `frontend/src/features/replay/SettingsDrawer.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles/dashboard.css`
- Modify: `frontend/src/styles/features.css`
- Modify: `frontend/src/styles/responsive.css`

**Interfaces:**
- Produces: `ReviewDock = 'anchor' | 'left' | 'right'`, `parseReviewDock`, `readReviewDock`, and `writeReviewDock`.
- `TopBar` consumes `reviewDock`; `SettingsDrawer` consumes it and `onReviewDock`.

- [ ] **Step 1: Write the preference check**

Assert that `left` and `right` survive parsing while missing/invalid input becomes `anchor`. Add `check:review-dock` to `package.json`.

- [ ] **Step 2: Run it and observe the missing exports**

Run: `cd frontend && npm run check:review-dock`

Expected: failure because the preference API does not exist.

- [ ] **Step 3: Add the independent persisted preference**

Implement the type/parser/read/write helpers beside existing replay preferences. Do not add it to `DashboardLayout` or presets.

- [ ] **Step 4: Wire Settings and TopBar**

Keep state in `main.tsx`. Add an `ANCHOR / LEFT / RIGHT` group under Desktop Workspace and expose the value as `data-dock` on `.top-panels`.

- [ ] **Step 5: Implement deterministic desktop docking**

For `LEFT`, fix Highlights at 16 px and DOTD after it; for `RIGHT`, mirror the order from the right. Keep `ANCHOR` unchanged. At `max-width:1024px`, preserve the existing static drawer behavior.

- [ ] **Step 6: Raise active user-facing microcopy**

Change the 9–11 px labels in Timing header/actions, workspace controls, Battle Intelligence, review-panel kickers, Feed metadata, and strategy-adjacent controls to at least 12 px. Retain documented glyph/status-dot exceptions.

- [ ] **Step 7: Run focused and frontend static checks**

Run: `cd frontend && npm run check:review-dock && npm run lint && npm run build`

Expected: all exit 0.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/scripts/check-review-dock.ts frontend/src/features/replay/replayTypes.ts frontend/src/features/replay/TopBar.tsx frontend/src/features/replay/SettingsDrawer.tsx frontend/src/main.tsx frontend/src/styles/dashboard.css frontend/src/styles/features.css frontend/src/styles/responsive.css
git commit -m "polish dashboard review controls"
```

### Task 4: Start races at T−60 and identify recorder builds

**Files:**
- Modify: `backend/tests/test_recorder_schedule.py`
- Modify: `backend/racelens/recorder/schedule.py`
- Modify: `deploy/recorder/Dockerfile`
- Modify: `deploy/recorder/install.sh`
- Modify: `deploy/recorder/README.md`

**Interfaces:**
- `ScheduledSession.capture_from` returns `starts_at - 60 minutes` for `R`, otherwise `starts_at - 10 minutes`.
- Recorder images expose `org.opencontainers.image.revision=<full commit>`.

- [ ] **Step 1: Replace the schedule regression first**

Assert Race is due at T−60 but not T−61, while Qualifying remains due at T−10 but not T−11.

- [ ] **Step 2: Run the focused test and observe Race failure**

Run: `cd backend && python -m pytest -q tests/test_recorder_schedule.py`

Expected: the Race T−60 assertion fails against the current shared ten-minute constant.

- [ ] **Step 3: Implement the hybrid lead**

Use two named timedeltas and select by `self.kind == 'R'` in `capture_from`. Leave hard durations unchanged.

- [ ] **Step 4: Label the Docker image**

Add `ARG VCS_REF=unknown` and `LABEL org.opencontainers.image.revision=$VCS_REF`. Pass the full repository SHA from `install.sh` while preserving the short-SHA tag.

- [ ] **Step 5: Update recorder operations documentation**

Document Race T−60, other sessions T−10, local-only raw growth, 14-day retention, and one inspect command that reports image, revision, health, user, and read-only status.

- [ ] **Step 6: Run the recorder schedule tests**

Run: `cd backend && python -m pytest -q tests/test_recorder_schedule.py`

Expected: all schedule tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_recorder_schedule.py backend/racelens/recorder/schedule.py deploy/recorder/Dockerfile deploy/recorder/install.sh deploy/recorder/README.md
git commit -m "start race capture one hour early"
```

### Task 5: Refresh public documentation and close the active list

**Files:**
- Modify: `README.md`
- Modify: `BACKLOG.md`
- Modify: `docs/superpowers/specs/2026-08-04-race-lens-ux-polish-design.md`
- Delete: `docs/superpowers/plans/2026-08-04-race-lens-ux-polish.md`

**Interfaces:**
- README remains the public product/technical entry point.
- BACKLOG remains the canonical owner-facing work list.

- [ ] **Step 1: Rewrite the README opening and demo path**

Lead with the replay experience, use short confident copy, replace the removed `ARCHIVE` instruction with session-catalog behavior, and avoid fabricated user/traffic claims.

- [ ] **Step 2: Make session coverage durable**

Replace the exhaustive bundled-data table with representative stories plus a note that the in-app catalog is authoritative. Preserve architecture, setup, security, API, evaluation, and disclaimer sections.

- [ ] **Step 3: Reconcile the backlog**

Mark tyre clarity, What to Watch focus, important type, popup docking, and the T−60 decision as done. Leave actual future-session production proof open.

- [ ] **Step 4: Check documentation and user-file safety**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; `CV_RACE_LENS_HANDOFF.md` remains untracked and unchanged.

- [ ] **Step 5: Commit**

```bash
git add README.md BACKLOG.md docs/superpowers/specs/2026-08-04-race-lens-ux-polish-design.md docs/superpowers/plans/2026-08-04-race-lens-ux-polish.md
git commit -m "refresh product docs and backlog"
```

### Task 6: Full verification, push, deploy, and cleanup

**Files:**
- Modify only concrete defects found by verification.

**Interfaces:**
- Produces a verified `main`, pushed Render deployment, and attributable recorder image instructions/build.

- [ ] **Step 1: Run the complete local matrix once**

```bash
cd backend && python -m pytest -q && ruff check racelens/ scripts/ tests/
cd ../frontend && npm run check:stints && npm run check:insight-focus && npm run check:review-dock && npm run check:ui && npm run check:track && npm run lint && npm run build
cd ../rust/race-core && cargo test
```

Expected: every command exits 0.

- [ ] **Step 2: Inspect the final diff and worktree**

Confirm only intended files differ from `origin/main`, the owner CV file remains untracked, and no secret or generated artifact is staged.

- [ ] **Step 3: Push `main`**

Run: `git push origin main`.

Expected: push succeeds and Render's commit-triggered deployment starts.

- [ ] **Step 4: Verify public deployment**

Poll `/api/ping`, then verify the served page contains the new build after Render finishes. Report cold-wake timing separately from correctness.

- [ ] **Step 5: Prepare or install the recorder build**

If the configured production recorder host is reachable, run its documented install from the current checkout and capture the image revision/health output. Otherwise report the exact install command and the external host-access blocker without claiming deployment.

- [ ] **Step 6: Remove the stale remote branch**

After proving `bfe6e80` and `main` trees remain identical for that patch, delete `origin/fix/replay-polish-followup` and confirm only active remote branches remain.

- [ ] **Step 7: Record the remaining production proof**

Keep the next real scheduled session observation open in BACKLOG. Do not mark it done based on unit tests or image deployment alone.
