import assert from 'node:assert/strict'
import { dotdResultOrder } from '../src/lib/driverOfDay.ts'

assert.deepEqual(
  dotdResultOrder(true, { driver: 'VER' }, 'NOR', 'LEC'),
  ['official', 'user', 'race-lens'],
)
assert.deepEqual(dotdResultOrder(true, null, null, 'LEC'), ['official-pending', 'race-lens'])
assert.deepEqual(dotdResultOrder(false, { driver: 'VER' }, 'NOR', 'LEC'), ['user', 'race-lens'])

console.log('DOTD result ordering check passed')
