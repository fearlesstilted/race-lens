# Task 5 report: Useful widget actions and configurable workspace

## Status

Complete. Desktop uses `react-grid-layout` 2.2.4 with schema-v2 Replay/Live
layouts, legacy migration, reset, visibility and density controls, header drag,
resize, and keyboard move/resize. The existing <=1024px workspace and mobile
tabs remain outside the grid.

Timing and strategy select one driver, battle rows select both drivers, Replay
feed rows seek only to their own timestamp and focus their driver when present,
and Live feed rows only focus. Non-driver Live feed rows remain inert.

## Review follow-up

All five Important review findings are closed. Keyboard movement now mutates
the selected item from the current grid layout and persists that position.
Feed-row activation and team radio are separate sibling buttons, with a direct
target guard protecting the row action. Timing has distinct full, compact, and
summary presentations, including an explicit-full override over container
queries; Track, Highlights, and DOTD now advertise only their implemented full
presentation. The mobile Battles/Track choice uses a dedicated storage key and
legacy migration, independent of Replay/Live desktop layouts. Remaining active
desktop 10px/11px copy in Live state, Live lobby, pit simulation, and what-if
rows is raised to 12px.

## Checks

- `npm run check:workspace` passed: schema-v2 migration, selected-item keyboard
  movement and persistence, independent Replay/Live and mobile-center storage,
  honest density selection, direct feed target isolation, reset, and action
  routing.
- `npm run build` passed: TypeScript and Vite production build, 106 modules.
- `git diff --check` passed.

No full matrix or lint run was performed, per the task brief.

## Limitations

- The requested command budget did not include browser automation, so the
  1680x1050 and 390px viewports were protected by the desktop breakpoint,
  bounded grid/CSS overflow rules, and 12px desktop overrides but were not
  screenshot-verified in this task.
- Pinned Highlights and DOTD intentionally reuse their existing on-demand
  expandable panels; no new review-panel behavior was added.
- `npm install` reported five dependency-tree audit findings (one low, four
  high). They were not auto-fixed because that would change unrelated packages.
