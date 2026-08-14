import assert from 'node:assert/strict'
import { recommendedReplay } from '../src/lib/recommendedReplay.ts'

assert.equal(recommendedReplay([
  'bahrain_2021_race',
  'hungarian_2026_race',
  'germany_2019_race',
]), 'hungarian_2026_race', 'Hungary 2026 is the first demo choice when ready')

assert.equal(recommendedReplay([
  'germany_2019_race',
  'bahrain_2021_race',
]), 'bahrain_2021_race', 'Bahrain 2021 is the fallback when Hungary is unavailable')

assert.equal(recommendedReplay([
  'belgian_2026_fp1',
  'germany_2019_race',
  'belgian_2026_qualifying',
]), 'germany_2019_race', 'the first ready Race is the final fallback')

assert.equal(recommendedReplay(['belgian_2026_fp1']), null, 'practice alone is not a replay CTA')

console.log('demo entry recommendation checks passed')
