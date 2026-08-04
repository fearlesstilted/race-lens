# Race Lens UX Polish Design

**Status:** Approved direction A on 2026-08-04

## Goal

Make the replay interface readable and intentional by removing implementation
copy, eliminating weak features, increasing the minimum text size, and reducing
the timeline and analytics panels to information that helps somebody follow a
race.

## Design direction

The interface remains an industrial broadcast desk, but it stops behaving like
an engineering diagnostics screen. The pass is deletion-first: if a label only
explains the implementation, repeats information, or apologizes for an
uncalibrated metric, it is removed instead of restyled.

No dependency or new design system is added. Existing React components, CSS
variables, archive dialog, persisted workspace state, and browser controls are
reused.

## Typography

- Barlow Condensed remains the interface and data face.
- Inter is used only for sentence-length explanatory copy.
- Secondary labels are at least 12px; section labels are 13–14px; ordinary copy
  is at least 14px; primary data remains 16px or larger.
- Letter spacing is reduced where it harms recognition. Tiny 7–10px uppercase
  text is not retained.
- The same scale applies across the header, timing tower, race intelligence,
  archive, strategy, insights, and replay controls.

## Header and session selection

The three browser-native session selects and the metadata line are replaced by
one clear session trigger, for example `2026 · HUNGARY · RACE`. Activating it
opens the existing accessible Session Catalog; a second custom listbox is not
built.

The separate `ARCHIVE` button, selected `REPLAY` button, `source: fixture`
metadata, and header language controls are removed. Language and mode remain in
Settings. `LIVE` is shown only when live mode is available. `HIGHLIGHTS` and
`LAYERS` remain.

DOTD is removed from both the desktop header and Settings. Its component and
dead styling are removed rather than hidden.

## Race workspace

A visible `BATTLES | TRACK` switch is placed at the center view boundary and
uses the existing persisted `dashboardLayout.center` value. This makes the map
discoverable without navigating through Layers, Settings, and Desktop
Workspace. On mobile, the tab names the active view instead of the ambiguous
`RACE` label.

The timing tower uses larger headers and controls. An empty tower is simply
empty; `No data` is removed.

`WHAT TO WATCH` and its category chips are enlarged. The empty insight card no
longer carries the meaningless `INFO` badge.

## Battle Intelligence

The page heading loses `OFFICIAL ORDER · MEASURED GAPS · RACE CONTEXT` and `NO
INFERRED TRACK POSITION`. Formation state keeps only `SESSION READY` and
`FORMATION LAP`; the instruction paragraph is removed.

The four cards become:

- `TOP 3`: current top three and measured gaps. `CONFIRMED` is removed; an
  attack-range callout appears only when it is true.
- `RACE`: lap, leader, fastest lap, and running-car count. Duplicate track,
  battle, and provenance cells are removed.
- `ACTIVE BATTLES`: count is part of the heading. The empty state reads `No
  active battles right now.` at a readable size.
- `5-LAP PACE`: ranked rows show driver, average time, and delta. The vague
  normalized bars and `LOWER IS BETTER` are removed. Before a completed lap,
  the panel reads `Complete a lap to compare pace.`

## Tyre strategy

The strategy remains because it communicates real race information. It gains a
compact S/M/H/I/W legend, a lap ruler, taller bars, clearer gaps between stints,
and direct labels containing compound and lap range when space permits.

Rendered stints are clipped to the replay's current lap. The current component
exposes the final race strategy at lap one, which violates the replay's
spoiler-free behavior. Scrubbing forward progressively reveals the strategy.
Loading and unavailable states are explicit and readable.

## Gap score removal

`GAP SCORE`, its Settings/Layer toggle, center tab, and graph are removed from
the user interface. The score is uncalibrated, ignores tyres and pace, and can
render a single flat 100 line; presenting it as analysis reduces trust. Backend
code is not expanded or redesigned in this pass.

## Replay controls and timeline

The timeline becomes one calm scrub surface:

- a native range input provides pointer and keyboard scrubbing;
- the SC/VSC/red-flag phase band remains as the only event layer;
- individual incident, overtake, undercut, and fastest-lap glyphs are removed;
- event jumping remains available through Highlights;
- the current lap/time label remains readable above the scrubber;
- Play/Pause becomes a centered icon-only square with its existing dynamic
  accessible label;
- 1×/5×/10× remain and are exposed as one labelled control group.

No new timeline modes, legends, or marker-density settings are added.

## Archive

The archive worker explanation and `RACE ARCHIVE · 2018—NOW` kicker are removed.
Round numbers rise to 12px and Grand Prix names to 20px. Queue and processing
state stay on the session buttons where they are actionable.

## Responsive and accessibility requirements

- Desktop, 1024px, and 390px layouts must not overflow horizontally.
- Interactive controls retain at least a 44px touch target on mobile.
- The session trigger opens the existing focus-contained catalog dialog.
- The center view switch exposes pressed state and works with keyboard input.
- Native range semantics replace the hand-built timeline slider semantics.
- Removing visible Play/Pause text does not remove its accessible name.
- Tyre strategy information is not color-only on touch devices.

## Requirement coverage

| User item | Design resolution |
|---|---|
| 1 | One larger session trigger; metadata removed; shared type scale |
| 2 | Timing/header sizes raised; `No data` removed |
| 3 | Existing custom archive dialog replaces native header selects |
| 4 | Battle Intelligence implementation kicker removed |
| 5 | Formation instruction removed |
| 6 | `NO INFERRED TRACK POSITION` removed |
| 7 | DOTD removed; header alignment simplified |
| 8 | What to Watch heading and filters enlarged |
| 9 | Empty insight `INFO` badge removed |
| 10 | Archive worker notice removed |
| 11 | Round labels and race names enlarged |
| 12 | Archive kicker removed |
| 13 | Play/Pause normalized to centered icon-only control |
| 14 | `LEAD FLOW · OFFICIAL ORDER` becomes `TOP 3` |
| 15 | `CONFIRMED`, duplicated `GREEN`, `LOWER IS BETTER`, and `0 GROUPS` removed or merged |
| 16 | Battle/Pace headings and empty states rewritten and enlarged |
| 17 | Race summary reduced to three readable stats |
| 18 | Tyre strategy clarified, enlarged, and made spoiler-safe |
| 19 | Uncalibrated gap graph removed |
| 20 | Timeline reduced to phase band, scrubber, cursor, and essential controls |
| Map | Visible persisted `BATTLES | TRACK` switch |

## Verification

- Add focused checks for removed copy, session-trigger behavior, view switching,
  spoiler-safe stint clipping, and timeline scrubbing.
- Run frontend lint, UI checks, track checks, and production build.
- Exercise the selection dialog, Battles/Track switch, scrubber keyboard input,
  and strategy reveal at early/mid/late race times.
- Capture desktop and 390px screenshots and compare each of the 25 supplied
  crops against the implemented state.

## Out of scope

Freeform draggable/resizable windows, Windows packaging, terminal rendering,
demo recording, and the next production live-capture validation remain separate
work. This pass only removes overload and makes the existing replay coherent.
