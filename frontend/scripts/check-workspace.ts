import assert from 'node:assert/strict'
import {
  WORKSPACE_KEY,
  WIDGET_REGISTRY,
  applyWorkspaceLayout,
  defaultWorkspace,
  isDirectActivation,
  moveWorkspaceItem,
  readDeskPreferences,
  readMobileCenter,
  readWorkspaces,
  resetWorkspace,
  selectDensity,
  toggleDriverFocus,
  updateWorkspaceWidget,
  workspaceAction,
  writeDeskPreference,
  writeMobileCenter,
  writeWorkspace,
} from '../src/features/replay/workspace.ts'

assert.equal(typeof toggleDriverFocus, 'function', 'shared timing selection transition exists')
assert.deepEqual(toggleDriverFocus([], 'NOR'), ['NOR'], 'one click selects a driver')
assert.deepEqual(toggleDriverFocus(['NOR'], 'VER'), ['NOR', 'VER'], 'a second driver creates Head-to-Head')
assert.deepEqual(toggleDriverFocus(['NOR', 'VER'], 'NOR'), ['VER'], 'clicking a selected driver removes it')
assert.deepEqual(toggleDriverFocus(['NOR', 'VER'], 'LEC'), ['VER', 'LEC'], 'a third driver replaces the oldest')

class MemoryStorage {
  readonly values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

assert.equal(typeof readDeskPreferences, 'function', 'desk preferences have a separate reader')
assert.equal(typeof writeDeskPreference, 'function', 'desk preferences have a separate writer')
const deskStorage = new MemoryStorage()
assert.deepEqual(readDeskPreferences(deskStorage), { replay: 'classic', live: 'classic' },
  'new and migrated installations default both modes to Classic')
writeDeskPreference('replay', 'custom', deskStorage)
assert.deepEqual(readDeskPreferences(deskStorage), { replay: 'custom', live: 'classic' },
  'Replay desk choice does not change Live')
writeDeskPreference('live', 'custom', deskStorage)
assert.deepEqual(readDeskPreferences(deskStorage), { replay: 'custom', live: 'custom' },
  'Live desk choice persists independently')
assert.equal(deskStorage.getItem(WORKSPACE_KEY), null, 'desk preferences do not write workspace schema v2')

const migratedStorage = new MemoryStorage()
migratedStorage.setItem('racelens_dashboard_layout', JSON.stringify({
  center: 'track',
  timing: false,
  insights: true,
  feed: false,
}))
const migrated = readWorkspaces(migratedStorage)
assert.equal(migrated.version, 2)
assert.equal(migrated.replay.widgets.timing.visible, false)
assert.equal(migrated.replay.widgets.track.visible, true)
assert.equal(migrated.replay.widgets.battles.visible, false)
assert.equal(migrated.replay.widgets.feed.visible, false)
assert.ok(migratedStorage.getItem(WORKSPACE_KEY), 'migration persists schema v2')
assert.equal(migratedStorage.getItem('racelens_dashboard_layout'), null, 'legacy layout migrates once')

assert.equal(readMobileCenter(migratedStorage), 'track', 'legacy center survives schema-v2 migration')

const storage = new MemoryStorage()
const classicDerived = defaultWorkspace('replay')
assert.deepEqual(
  { x: classicDerived.widgets.insights.x, y: classicDerived.widgets.insights.y, w: classicDerived.widgets.insights.w, h: classicDerived.widgets.insights.h },
  { x: 8, y: 0, w: 4, h: 14 },
  'Custom reset keeps Insights readable in the Classic right column',
)
const replay = updateWorkspaceWidget(defaultWorkspace('replay'), 'replay', 'track', { visible: false })
writeWorkspace('replay', replay, storage)
const live = updateWorkspaceWidget(defaultWorkspace('live'), 'live', 'feed', { visible: false })
writeWorkspace('live', live, storage)
assert.equal(readWorkspaces(storage).replay.widgets.track.visible, false)
assert.equal(readWorkspaces(storage).live.widgets.feed.visible, false)
resetWorkspace('replay', storage)
assert.equal(readWorkspaces(storage).replay.widgets.track.visible, false, 'Custom reset mirrors Classic Battles-first layout')
assert.equal(readWorkspaces(storage).live.widgets.feed.visible, false, 'Replay reset leaves Live untouched')

writeMobileCenter('track', storage)
writeWorkspace('replay', defaultWorkspace('replay'), storage)
assert.equal(readMobileCenter(storage), 'track', 'desktop layout writes do not replace the mobile center')

const keyboardWorkspace = defaultWorkspace('replay')
const keyboardLayout = [
  { ...keyboardWorkspace.widgets.timing },
  { ...keyboardWorkspace.widgets.track },
]
const movedLayout = moveWorkspaceItem(keyboardLayout, 'timing', 1, 0)
assert.equal(movedLayout.find((item) => item.i === 'timing')?.x, 1, 'selected keyboard item moves')
assert.equal(movedLayout.find((item) => item.i === 'track')?.x, 8, 'unrelated item remains in place')
const keyboardStorage = new MemoryStorage()
writeWorkspace('replay', applyWorkspaceLayout(keyboardWorkspace, 'replay', movedLayout), keyboardStorage)
assert.equal(readWorkspaces(keyboardStorage).replay.widgets.timing.x, 1, 'selected keyboard move persists')

const densities = ['auto', 'full', 'compact', 'summary'] as const
assert.equal(selectDensity(620, 360, densities, 'auto'), 'full')
assert.equal(selectDensity(390, 260, densities, 'auto'), 'compact')
assert.equal(selectDensity(250, 150, densities, 'auto'), 'summary')
assert.equal(selectDensity(620, 360, densities, 'compact'), 'compact', 'override wins')
assert.equal(selectDensity(250, 150, WIDGET_REGISTRY.timing.densities, 'full'), 'full', 'explicit timing full wins at narrow sizes')
for (const id of ['track', 'highlights', 'dotd'] as const) {
  assert.equal(
    selectDensity(250, 150, WIDGET_REGISTRY[id].densities, 'auto'),
    'full',
    `${id} only advertises its implemented full presentation`,
  )
}

const rowAction = {}
const radioButton = {}
assert.equal(isDirectActivation(rowAction, rowAction), true, 'the row action handles its own activation')
assert.equal(isDirectActivation(rowAction, radioButton), false, 'a radio-button activation cannot trigger the row action')

assert.deepEqual(workspaceAction('replay', 'battle', ['NOR', 'VER', 'LEC']), { focusIds: ['NOR', 'VER'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'strategy', ['PIA']), { focusIds: ['PIA'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'feed', ['HAM'], 42_500), { focusIds: ['HAM'], seekMs: 42_500 })
assert.deepEqual(workspaceAction('live', 'feed', ['HAM'], 42_500), { focusIds: ['HAM'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'feed', [], 42_500), { focusIds: [], seekMs: 42_500 })

console.log('workspace schema, keyboard, density, persistence, mobile, and action checks passed')
