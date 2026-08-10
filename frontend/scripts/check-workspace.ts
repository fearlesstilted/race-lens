import assert from 'node:assert/strict'
import {
  WORKSPACE_KEY,
  defaultWorkspace,
  readWorkspaces,
  resetWorkspace,
  selectDensity,
  updateWorkspaceWidget,
  workspaceAction,
  writeWorkspace,
} from '../src/features/replay/workspace.ts'

class MemoryStorage {
  readonly values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

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

const storage = new MemoryStorage()
const replay = updateWorkspaceWidget(defaultWorkspace('replay'), 'replay', 'track', { visible: false })
writeWorkspace('replay', replay, storage)
const live = updateWorkspaceWidget(defaultWorkspace('live'), 'live', 'feed', { visible: false })
writeWorkspace('live', live, storage)
assert.equal(readWorkspaces(storage).replay.widgets.track.visible, false)
assert.equal(readWorkspaces(storage).live.widgets.feed.visible, false)
resetWorkspace('replay', storage)
assert.equal(readWorkspaces(storage).replay.widgets.track.visible, true, 'reset restores Replay default')
assert.equal(readWorkspaces(storage).live.widgets.feed.visible, false, 'Replay reset leaves Live untouched')

const densities = ['auto', 'full', 'compact', 'summary'] as const
assert.equal(selectDensity(620, 360, densities, 'auto'), 'full')
assert.equal(selectDensity(390, 260, densities, 'auto'), 'compact')
assert.equal(selectDensity(250, 150, densities, 'auto'), 'summary')
assert.equal(selectDensity(620, 360, densities, 'compact'), 'compact', 'override wins')

assert.deepEqual(workspaceAction('replay', 'timing', ['NOR']), { focusIds: ['NOR'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'battle', ['NOR', 'VER', 'LEC']), { focusIds: ['NOR', 'VER'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'strategy', ['PIA']), { focusIds: ['PIA'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'feed', ['HAM'], 42_500), { focusIds: ['HAM'], seekMs: 42_500 })
assert.deepEqual(workspaceAction('live', 'feed', ['HAM'], 42_500), { focusIds: ['HAM'], seekMs: null })
assert.deepEqual(workspaceAction('replay', 'feed', [], 42_500), { focusIds: [], seekMs: 42_500 })

console.log('workspace schema, density, persistence, reset, and action checks passed')
