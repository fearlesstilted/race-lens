import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { withApiBase } from '../src/api/url.ts'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (path: string) => readFileSync(resolve(root, path), 'utf8')

assert.equal(withApiBase('/api/ping', ''), '/api/ping')
assert.equal(
  withApiBase('/api/ping', 'https://race-lens.onrender.com/'),
  'https://race-lens.onrender.com/api/ping',
)
assert.throws(() => withApiBase('https://example.com/api/ping'))

const config = JSON.parse(read('src-tauri/tauri.conf.json'))
assert.deepEqual(config.bundle.targets, ['nsis'])
assert.equal(config.build.beforeBuildCommand, 'npm run build:desktop')
assert.match(config.app.security.csp, /https:\/\/race-lens\.onrender\.com/)

const api = read('../backend/racelens/api.py')
for (const origin of [
  'https://race-lens.onrender.com',
  'http://tauri.localhost',
  'tauri://localhost',
  'http://localhost:5173',
]) assert.match(api, new RegExp(`"${origin.replaceAll('.', '\\.')}"`))
assert.doesNotMatch(api, /allow_origins=\["\*"\]/)

const workflow = read('../.github/workflows/desktop-release.yml')
assert.match(workflow, /desktop-v\*/)
assert.match(workflow, /windows-latest/)
assert.match(workflow, /x86_64-pc-windows-msvc/)

console.log('Desktop URL, CORS, Tauri, and release config check passed')
