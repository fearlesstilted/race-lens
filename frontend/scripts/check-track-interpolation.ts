import assert from 'node:assert/strict'

import { progressPathPosition } from '../src/lib/trackInterpolation.ts'

const square: [number, number][] = [[0, 0], [10, 0], [10, 10], [0, 10]]

const midpoint = progressPathPosition([0.1, 0.2], square, 0.5)
assert(midpoint)
assert(Math.abs(midpoint[0] - 6) < 1e-9)
assert.equal(midpoint[1], 0)
assert.deepEqual(progressPathPosition([0.95, 1.05], square, 0.5), [0, 0])
assert.equal(progressPathPosition([null], square, 0), null)
assert.equal(progressPathPosition([0.1, 0.5], square, 0.5), null)
assert.equal(progressPathPosition([0.5, 0.4], square, 0.5), null)

const line = Array.from({ length: 100 }, (_, index) => [index, 0] as [number, number])
const uneven = [0, 0.01, 0.04, 0.05, 0.06]
const samples = Array.from(
  { length: 61 },
  (_, index) => progressPathPosition(uneven, line, 1 + index / 30)?.[0],
)
assert(samples.every((sample) => sample !== undefined))
assert(samples.every((sample, index) => index === 0 || sample! >= samples[index - 1]!))
const leftVelocity = samples[30]! - samples[29]!
const rightVelocity = samples[31]! - samples[30]!
assert(Math.abs(leftVelocity - rightVelocity) < 0.002)

console.log('track interpolation check passed')
