import assert from 'node:assert/strict'

import { focusDriverIds } from '../src/lib/insightFocus.ts'

assert.deepEqual(focusDriverIds(['NOR', 'VER', 'NOR', 'LEC']), ['NOR', 'VER'])
assert.deepEqual(focusDriverIds(['', '  ', 'HAM']), ['HAM'])
assert.deepEqual(focusDriverIds([]), [])

console.log('insight focus check passed')
