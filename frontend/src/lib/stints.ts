import type { Stint } from '../api/types'

export function clipStints(stints: Stint[], currentLap: number): Stint[] {
  return stints.flatMap((stint) => {
    if (stint.start_lap > currentLap) return []
    if (stint.end_lap <= currentLap) return [stint]
    const end_lap = currentLap
    return [{ ...stint, end_lap, laps: end_lap - stint.start_lap + 1 }]
  })
}

export function showStintLabel(laps: number, totalLaps: number): boolean {
  return totalLaps > 0 && laps / totalLaps >= 0.08
}
