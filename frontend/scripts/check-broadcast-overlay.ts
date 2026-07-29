import assert from 'node:assert/strict'

import { selectBroadcastCandidate } from '../src/lib/broadcastOverlay.ts'

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

console.log('broadcast overlay check passed')
