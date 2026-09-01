import assert from 'node:assert/strict'

const companion = await import('../src/api/companion.ts').catch(() => null)
assert.ok(companion, 'companion synchronization interface exists')

const {
  initialCompanionSync,
  parseCompanionInvite,
  resolvePendingLiveNavigation,
  shareCompanionUrl,
  transitionCompanion,
} = companion

assert.equal(typeof parseCompanionInvite, 'function', 'companion fragment capture exists')
assert.equal(typeof shareCompanionUrl, 'function', 'public companion link builder exists')
assert.deepEqual(
  parseCompanionInvite(new URL('https://race-lens.onrender.com/companion/link-1#token=secret-value')),
  { linkId: 'link-1', secret: 'secret-value', cleanPath: '/companion/link-1' },
  'the secret is captured from the fragment and the clean URL excludes it',
)
assert.equal(
  shareCompanionUrl({ linkId: 'link-1', secret: 'secret-value' }),
  'https://race-lens.onrender.com/companion/link-1#token=secret-value',
)
let malformedInvite: unknown = 'threw'
try {
  malformedInvite = parseCompanionInvite(new URL('https://race-lens.onrender.com/companion/%E0%A4%A#token=secret'))
} catch { /* assertion below reports the startup failure */ }
assert.equal(malformedInvite, null, 'a malformed public path is ignored instead of breaking app startup')

const replayState = {
  race_id: 'bahrain_2021_race',
  mode: 'replay' as const,
  at_ms: 42_000,
  selected_driver_ids: ['NOR', 'VER'],
}
const snapshot = {
  link_id: 'link-1',
  revision: 1,
  expires_at: '2026-09-01T13:00:00Z',
  state: replayState,
}

const remote = transitionCompanion(initialCompanionSync(), { type: 'remote', snapshot })
assert.equal(remote.sync.status, 'linked')
assert.deepEqual(remote.effects.filter((effect) => effect.type === 'patch'), [],
  'applying a remote snapshot never echoes it back')
assert.deepEqual(remote.effects[0], { type: 'apply', state: replayState })

const beforeInitial = transitionCompanion(initialCompanionSync(), {
  type: 'local',
  state: null,
  action: { at_ms: 55_000 },
})
assert.deepEqual(beforeInitial.effects, [], 'a pre-initial action waits for the first snapshot')
const initialWithPending = transitionCompanion(beforeInitial.sync, {
  type: 'remote',
  snapshot: { ...snapshot, revision: 0 },
})
assert.deepEqual(initialWithPending.effects, [
  { type: 'apply', state: replayState },
  { type: 'apply', state: { ...replayState, at_ms: 55_000 } },
  { type: 'patch', expected_revision: 0, state: { ...replayState, at_ms: 55_000 } },
], 'the first snapshot is applied before one pending local action and one PATCH')
const initialConflict = transitionCompanion(initialWithPending.sync, {
  type: 'conflict',
  snapshot: { ...snapshot, revision: 1, state: { ...replayState, at_ms: 1_000, selected_driver_ids: [] } },
})
assert.equal(initialConflict.effects.some((effect) => effect.type === 'patch'), false,
  'a pre-initial action never creates a conflict retry loop')

const staleState = { ...replayState, at_ms: 1_000, selected_driver_ids: [] }
const staleRemote = transitionCompanion(remote.sync, {
  type: 'remote',
  snapshot: { ...snapshot, revision: 0, state: staleState },
})
assert.equal(staleRemote.sync.revision, 1, 'a stale long-poll response cannot lower the revision')
assert.deepEqual(staleRemote.sync.state, replayState, 'a stale long-poll response cannot roll state backward')
assert.deepEqual(staleRemote.effects, [], 'a stale long-poll response is never applied')

const stalePatch = transitionCompanion(remote.sync, {
  type: 'patched',
  snapshot: { ...snapshot, revision: 0, state: staleState },
})
assert.equal(stalePatch.sync.revision, 1, 'a stale PATCH response cannot lower the revision')
assert.deepEqual(stalePatch.sync.state, replayState, 'a stale PATCH response cannot roll state backward')

const deselect = transitionCompanion(remote.sync, {
  type: 'local',
  state: replayState,
  action: { selected_driver_ids: ['VER'] },
})
assert.deepEqual(deselect.effects[0], {
  type: 'patch',
  expected_revision: 1,
  state: { ...replayState, selected_driver_ids: ['VER'] },
}, 'driver removal publishes the resulting selection')

const optimistic = { ...remote.sync, pending: deselect.sync.pending }
const heartbeat = transitionCompanion(optimistic, { type: 'remote', snapshot })
assert.deepEqual(heartbeat.sync.pending, optimistic.pending, 'an equal revision keeps the optimistic action pending')
assert.deepEqual(heartbeat.effects, [], 'an equal revision heartbeat never reapplies server state')

const conflictState = { ...replayState, at_ms: 84_000, selected_driver_ids: ['NOR'] }
const conflict = transitionCompanion(deselect.sync, {
  type: 'conflict',
  snapshot: { ...snapshot, revision: 2, state: conflictState },
})
assert.deepEqual(conflict.effects, [
  { type: 'apply', state: conflictState },
  { type: 'apply', state: { ...conflictState, selected_driver_ids: ['VER'] } },
  {
    type: 'patch',
    expected_revision: 2,
    state: { ...conflictState, selected_driver_ids: ['VER'] },
  },
], 'a conflict applies current state and reapplies the one local action once')

const secondConflict = transitionCompanion(conflict.sync, {
  type: 'conflict',
  snapshot: { ...snapshot, revision: 3, state: replayState },
})
assert.equal(secondConflict.effects.some((effect) => effect.type === 'patch'), false,
  'a repeated conflict cannot start a retry loop')

const reconnecting = transitionCompanion(remote.sync, { type: 'network-error' })
assert.equal(reconnecting.sync.status, 'reconnecting')
assert.equal(transitionCompanion(reconnecting.sync, { type: 'remote', snapshot }).sync.status, 'linked')
const expired = transitionCompanion(remote.sync, { type: 'expired' })
assert.equal(expired.sync.status, 'expired')
assert.equal(transitionCompanion(expired.sync, { type: 'leave' }).sync.status, 'disconnected')

const waitingLive = resolvePendingLiveNavigation(true, null, null)
assert.deepEqual(waitingLive, { pending: true, action: null }, 'explicit Live waits for a real identifier')
const directLive = resolvePendingLiveNavigation(waitingLive.pending, 'live-direct', 'live-canonical')
assert.deepEqual(directLive, {
  pending: false,
  action: { mode: 'live', race_id: 'live-direct', at_ms: null, selected_driver_ids: [] },
}, 'the direct Live session identifier wins when available')
assert.equal(resolvePendingLiveNavigation(directLive.pending, 'live-direct', null).action, null,
  'the explicit Live navigation publishes exactly once')
assert.equal(resolvePendingLiveNavigation(false, 'remote-live', null).action, null,
  'remote Live application never starts a publish')

console.log('companion synchronization checks passed')
