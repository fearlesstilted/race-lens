import assert from 'node:assert/strict'

import { selectBroadcastCandidate } from '../src/lib/broadcastOverlay.ts'
import { battleGap, battlePair } from '../src/lib/battles.ts'
import { livePresentation } from '../src/lib/liveStatus.ts'

const incident = {
  kind: 'CRASH' as const,
  at_ms: 10_000,
  lap: 2,
  driver_ids: ['1'],
  text_en: 'Crash',
  text_ru: 'Авария',
}
const radio = {
  id: 'radio',
  at_ms: 14_000,
  lap: 2,
  tag: 'RADIO',
  text: 'RADIO: all good',
  audio_url: '/radio.mp3',
}

assert.equal(selectBroadcastCandidate({
  atMs: 15_000,
  playing: true,
  speed: 1,
  lang: 'en',
  markers: [incident],
  feed: [radio],
})?.title, 'Crash')

const waitingStatus = {
  is_running: true,
  poll_count: 3,
  events_total: 0,
  last_poll_ok: true,
  last_poll_unix: 1,
  last_new_event_unix: null,
  last_error: null,
  data_quality: 'stalled' as const,
}
const waiting = livePresentation(waitingStatus, false, null)
assert.equal(waiting.phase, 'waiting')
assert.equal(livePresentation({ ...waitingStatus, capture_alive: false }, false, null).phase, 'stalled')
assert.equal(livePresentation(null, true, 'offline').phase, 'reconnecting')

const battle = { driver_ids: ['NOR', 'PIA'], evidence: { interval_s: 0.91 } }
assert.deepEqual(battlePair(battle), ['NOR', 'PIA'])
assert.equal(battleGap(battle), 0.91)

console.log('replay/live UI checks passed')
