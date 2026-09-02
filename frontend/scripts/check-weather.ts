import assert from 'node:assert/strict'

import { formatWeather } from '../src/lib/weather.ts'

assert.equal(formatWeather(null), null)
assert.equal(formatWeather({ rainfall: true, track_temp_c: 32.9, air_temp_c: 18.7 }), 'RAIN · TRACK 32.9° · AIR 18.7°')
assert.equal(formatWeather({ rainfall: false, air_temp_c: 18.7 }), 'DRY · AIR 18.7°')

console.log('weather presentation checks passed')
