import assert from 'node:assert/strict'

import { clipStints } from '../src/lib/stints.ts'

const stints = [
  { compound: 'SOFT', start_lap: 1, end_lap: 10, laps: 10 },
  { compound: 'MEDIUM', start_lap: 11, end_lap: 20, laps: 10 },
  { compound: 'HARD', start_lap: 21, end_lap: 30, laps: 10 },
]

assert.deepEqual(clipStints(stints, 13), [
  stints[0],
  { compound: 'MEDIUM', start_lap: 11, end_lap: 13, laps: 3 },
])

console.log('stint clipping check passed')
