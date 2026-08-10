import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dotdResultOrder } from '../src/lib/driverOfDay.ts'

assert.deepEqual(
  dotdResultOrder(true, { driver: 'VER' }, 'NOR', 'LEC'),
  ['official', 'user', 'race-lens'],
)
assert.deepEqual(dotdResultOrder(true, null, null, 'LEC'), ['official-pending', 'race-lens'])
assert.deepEqual(dotdResultOrder(false, { driver: 'VER' }, 'NOR', 'LEC'), ['user', 'race-lens'])

const panel = readFileSync(new URL('../src/features/replay/DriverOfDayPanel.tsx', import.meta.url), 'utf8')
assert.match(panel, /\[sessionId, isFinished\]/, 'finish phase must trigger one final DOTD fetch')
assert.doesNotMatch(panel, /\[sessionId, isFinished, atMs\]/, 'ordinary clock ticks must not refetch DOTD')

console.log('DOTD result ordering check passed')
