import type { Battle } from '../api/types'

type BattleData = Pick<Battle, 'driver_ids' | 'evidence'>

export const battlePair = (battle: BattleData): [string, string] | null =>
  battle.driver_ids.length >= 2 ? [battle.driver_ids[0], battle.driver_ids[1]] : null

export const battleGap = (battle: BattleData): number | null =>
  typeof battle.evidence.interval_s === 'number' ? battle.evidence.interval_s : null
