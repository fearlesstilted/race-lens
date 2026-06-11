/**
 * Pure dead-reckoning math for the schematic track map. Advances a car's
 * fractional lap position by wall-time, then eases toward the target fraction.
 */
import type { DriverState } from '../api/types'
import { median } from './trackGeometry'

// Correction smoothing tau in ms — how fast current_frac catches up to target_frac
export const CORRECTION_TAU_MS = 2000

// Dead-reckoning speed multiplier while a safety car / VSC neutralises the field.
export const SC_SPEED_MULTIPLIER = 0.6

// If a target fraction jumps more than half a lap, snap directly instead of easing.
export const HALF_LAP_SNAP = 0.5

/**
 * Advance a single car's fractional lap position by one rAF tick.
 *
 * @param current     Current fraction [0, 1)
 * @param target      Latest computed target fraction [0, 1)
 * @param dtMs        Wall-clock ms since last tick
 * @param speed       Playback speed multiplier
 * @param lapMs       Estimated lap time in ms for this car
 * @param drMultiplier Dead-reckoning speed multiplier (e.g. 0 under red flag)
 */
export function advanceFraction(
  current: number,
  target: number,
  dtMs: number,
  speed: number,
  lapMs: number,
  drMultiplier: number,
): number {
  // Dead reckoning: advance car by wall-time * speed / lap_ms
  const drDelta = (dtMs * speed * drMultiplier) / lapMs
  const afterDR = (current + drDelta) % 1

  // Soft correction toward target (circular, shortest path)
  let corrDelta = ((target - afterDR) % 1 + 1) % 1
  if (corrDelta > HALF_LAP_SNAP) corrDelta -= 1 // allow backward correction

  if (Math.abs(corrDelta) > HALF_LAP_SNAP) {
    // Large snap (position data jump > half lap) — snap immediately
    return target
  }
  const corrK = 1 - Math.exp(-dtMs / CORRECTION_TAU_MS)
  return ((afterDR + corrDelta * corrK) % 1 + 1) % 1
}

/** Dead-reckoning speed multiplier for a session status. */
export function statusDrMultiplier(status: string): number {
  if (status === 'red_flag') return 0
  if (status === 'safety_car' || status === 'virtual_safety_car' || status === 'vsc') {
    return SC_SPEED_MULTIPLIER
  }
  return 1
}

/** Compute target fractions for all on-track drivers. Returns a map driverId → frac (0..1). */
export function computeTargetFractions(
  atMs: number,
  drivers: Record<string, DriverState>,
  classification: string[],
): Map<string, number> {
  const result = new Map<string, number>()

  const lapTimes = classification
    .map((id) => drivers[id]?.last_lap_ms)
    .filter((v): v is number => v !== null && v !== undefined && v > 0)
  const avgLapMs = median(lapTimes)

  const leaderFrac = (atMs % avgLapMs) / avgLapMs

  const onTrack: string[] = []
  for (const id of classification) {
    if (!drivers[id]?.in_pit && !drivers[id]?.retired) onTrack.push(id)
  }

  const knownGap: string[] = []
  const unknownGap: string[] = []
  for (const id of onTrack) {
    const d = drivers[id]
    if (!d) continue
    if (d.position === 1 || d.gap_s !== null) knownGap.push(id)
    else unknownGap.push(id)
  }

  const lastKnownGap = knownGap.length > 0
    ? (drivers[knownGap[knownGap.length - 1]]?.gap_s ?? 0)
    : 0

  for (const driverId of onTrack) {
    const d = drivers[driverId]
    if (!d) continue

    let gapFrac: number
    if (d.position === 1) {
      gapFrac = 0
    } else if (d.gap_s !== null) {
      gapFrac = (d.gap_s * 1000) / avgLapMs
    } else {
      const unknownIdx = unknownGap.indexOf(driverId)
      const baseGap = lastKnownGap * 1000
      gapFrac = (baseGap + (unknownIdx + 1) * 1000) / avgLapMs
    }

    const frac = ((leaderFrac - gapFrac) % 1 + 1) % 1
    result.set(driverId, frac)
  }

  return result
}
