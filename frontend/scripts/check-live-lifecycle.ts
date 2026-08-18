import assert from 'node:assert/strict'

import type { LiveStatusResult } from '../src/api/client.ts'
import { liveLifecycle, livePresentation } from '../src/lib/liveStatus.ts'

const remoteLive: LiveStatusResult = {
  is_running: true,
  poll_count: 12,
  events_total: 200,
  last_poll_ok: true,
  last_poll_unix: 1_786_310_400,
  last_new_event_unix: 1_786_310_399,
  last_error: null,
  data_quality: 'good',
  source: 'remote',
  status: 'live',
  canonical_session_id: '2026-15-r',
  replay_session_id: 'dutch_2026_race',
  generated_at: '2026-08-10T12:00:00Z',
  expires_at: '2026-08-10T12:00:20Z',
  capture_freshness: {
    raw_size: 1024,
    raw_updated_at: '2026-08-10T11:59:59Z',
    seconds_since_growth: 1,
    transport_growing: true,
  },
  failure: null,
}

assert.equal(liveLifecycle(remoteLive, {
  readonly: true,
  explicitReplay: false,
  attachedToLive: false,
}).enterLive, true, 'no-query production visit adopts active Live')

const explicitReplay = liveLifecycle(remoteLive, {
  readonly: true,
  explicitReplay: true,
  attachedToLive: false,
})
assert.equal(explicitReplay.enterLive, false, 'explicit replay is not hijacked')
assert.equal(explicitReplay.showLiveNow, true, 'explicit replay offers LIVE NOW')

const localLive: LiveStatusResult = {
  is_running: true,
  poll_count: 4,
  events_total: 20,
  last_poll_ok: true,
  last_poll_unix: 1_786_310_400,
  last_new_event_unix: 1_786_310_399,
  last_error: null,
  data_quality: 'good',
}
const idle = { ...localLive, is_running: false, status: 'idle' as const }
assert.equal(livePresentation(idle, false, null).badge, 'LIVE OFF')
assert.equal(liveLifecycle(localLive, {
  readonly: false,
  explicitReplay: false,
  attachedToLive: false,
}).enterLive, true, 'F5 reattaches to local Live')

assert.equal(livePresentation(
  { ...remoteLive, expires_at: '2026-08-10T11:59:59Z' },
  true,
  'offline',
  Date.parse('2026-08-10T12:00:00Z'),
).phase, 'stalled', 'expired snapshots stay stalled while EventSource reconnects')
assert.equal(livePresentation(
  remoteLive,
  true,
  'offline',
  Date.parse('2026-08-10T12:00:10Z'),
).phase, 'reconnecting')

const finishing = { ...remoteLive, is_running: false, status: 'finishing' as const }
assert.equal(liveLifecycle(finishing, {
  readonly: true,
  explicitReplay: false,
  attachedToLive: false,
}).enterLive, true, 'F5 during finishing reattaches to preparing state')
assert.equal(livePresentation(finishing, true, null).phase, 'preparing')
assert.equal(livePresentation(finishing, true, null).badge, 'REPLAY PREPARING')

const replayReady = { ...remoteLive, is_running: false, status: 'replay_ready' as const }
assert.equal(liveLifecycle(replayReady, {
  readonly: true,
  explicitReplay: false,
  attachedToLive: true,
}).replaySessionId, 'dutch_2026_race')

const failed = {
  ...remoteLive,
  is_running: false,
  status: 'failed' as const,
  failure: 'Archive preparation failed',
}
assert.equal(liveLifecycle(failed, {
  readonly: true,
  explicitReplay: false,
  attachedToLive: true,
}).replaySessionId, null, 'failure never fakes replay readiness')
assert.equal(livePresentation(failed, true, null).phase, 'failed')

assert.equal(liveLifecycle(remoteLive, {
  readonly: true,
  explicitReplay: false,
  attachedToLive: true,
}).canManage, false, 'readonly deployments expose no management actions')
assert.equal(liveLifecycle(remoteLive, {
  readonly: false,
  explicitReplay: false,
  attachedToLive: true,
}).canManage, false, 'remote Live exposes no management actions on writable deployments')
assert.equal(liveLifecycle(localLive, {
  readonly: false,
  explicitReplay: false,
  attachedToLive: true,
}).canManage, true)

console.log('production Live lifecycle checks passed')
