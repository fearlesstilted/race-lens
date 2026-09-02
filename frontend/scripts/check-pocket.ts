import assert from 'node:assert/strict'

const pocket = await import('../src/api/pocket.ts').catch(() => null)
assert.ok(pocket, 'Pocket handoff module exists')

const target = { version: 1, mode: 'replay' as const, sessionId: 'spa_2026_race', atMs: 12_000, focusedDrivers: ['VER', 'NOR'] }
const url = pocket.encodePocketLink(target)
assert.deepEqual(pocket.parsePocketLink(new URL(url)), target)
assert.equal(pocket.encodePocketAppLink(target), 'racelens://pocket?v=1&mode=replay&session=spa_2026_race&at=12000&drivers=VER%2CNOR')
assert.deepEqual(pocket.pocketBootstrap({ ...target, mode: 'live', atMs: null }), { initialSessionId: null, explicitReplay: false, attachLive: true, replayPinned: false })
assert.equal(pocket.parsePocketLink(new URL('https://race-lens.onrender.com/pocket?v=1&mode=live&session=live&at=1')), null)
assert.equal(pocket.parsePocketLink(new URL('https://example.com/pocket?v=1&mode=live&session=live')), null)
console.log('Pocket handoff checks passed')
