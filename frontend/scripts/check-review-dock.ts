import assert from 'node:assert/strict'

import { parseReviewDock } from '../src/features/replay/replayTypes.ts'

assert.equal(parseReviewDock('left'), 'left')
assert.equal(parseReviewDock('right'), 'right')
assert.equal(parseReviewDock('anchor'), 'anchor')
assert.equal(parseReviewDock('floating'), 'anchor')
assert.equal(parseReviewDock(null), 'anchor')

console.log('review dock check passed')
