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

console.log('track interpolation check passed')
