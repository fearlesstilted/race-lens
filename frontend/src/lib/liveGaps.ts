/**
 * Live gap estimation from telemetry position data.
 *
 * Computes estimated INT/GAP values every tick by converting fractional
 * track positions to time gaps. Falls back to official values when
 * estimates diverge too far (lapped cars, data gaps).
 */

export type PositionsData = {
  session_id: string
  start_ms: number
  tick_ms: number
  viewbox: [number, number]
  drivers: Record<string, ([number, number] | null)[]>
}

export type DriverLike = {
  in_pit: boolean
  retired: boolean
  last_lap_ms: number | null
  gap_s: number | null
  interval_s: number | null
}

/** Maximum deviation between estimated and official gap before we fall back. */
const SANITY_THRESHOLD_S = 30

/** Fallback lap time used when no telemetry lap times are available (78s ≈ a typical F1 lap). */
export const DEFAULT_LAP_MS = 78000

/**
 * Telemetry fractions are considered degenerate when every estimated gap is below
 * this many seconds — too close to zero to be physically plausible for trailing cars.
 */
const DEGENERATE_GAP_S = 0.05

/** Threshold above which an official gap is "substantial" enough to contradict near-zero estimates. */
const SUBSTANTIAL_GAP_S = 1

function median(values: number[]): number {
  if (values.length === 0) return NaN
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

/**
 * Compute the fractional position within the current lap [0, 1) for a driver at atMs.
 *
 * The key insight: two cars running close together have nearly the same absolute
 * frame index, so dividing by totalFrames gives almost identical fractions → ~0 gap.
 * We must express each car's position as a fraction *within one lap*, not across
 * the entire race.
 *
 * We estimate frames-per-lap from the driver's last_lap_ms and tick_ms, then
 * compute frac = (frameIndex % framesPerLap) / framesPerLap.
 */
function interpolateFraction(
  posData: PositionsData,
  driverId: string,
  atMs: number,
  lapMs: number,
): number | null {
  const frames = posData.drivers[driverId]
  if (!frames || frames.length === 0) return null

  const relMs = atMs - posData.start_ms
  if (relMs < 0) return null

  const fi = relMs / posData.tick_ms
  const i0 = Math.floor(fi)
  if (i0 >= frames.length) return null

  const f0 = frames[i0]
  if (f0 === null) return null

  // Frames per lap derived from lap time and tick resolution
  const framesPerLap = lapMs / posData.tick_ms
  if (framesPerLap <= 0) return null

  const alpha = fi - i0

  // Position within current lap as a fraction [0, 1)
  const frac0 = (i0 % framesPerLap) / framesPerLap
  const frac1 = ((i0 + 1) % framesPerLap) / framesPerLap

  // Handle lap boundary wrap (frac1 could wrap near 0)
  if (frac1 < frac0) {
    // Crossing lap boundary — interpolate linearly without wrapping
    return frac0 + alpha * (1 - frac0)
  }

  return frac0 + alpha * (frac1 - frac0)
}

export type LiveGapResult = {
  /** Estimated gap to leader in seconds, or null if unavailable/skipped */
  gap_s: number | null
  /** Estimated interval to car ahead in seconds, or null if unavailable/skipped */
  interval_s: number | null
  /** Whether this estimate comes from telemetry (true) or official data (false) */
  fromTelemetry: boolean
}

/**
 * Compute live gap estimates for all drivers in the classification order.
 *
 * @param posData     Positions telemetry data
 * @param atMs        Current session time in ms
 * @param classification  Ordered list of driver IDs (P1 first)
 * @param drivers     Driver states (for in_pit/retired, last_lap_ms, official gaps)
 * @returns Map of driverId → {gap_s, interval_s, fromTelemetry}
 */
export function computeLiveGaps(
  posData: PositionsData | null,
  atMs: number,
  classification: string[],
  drivers: Record<string, DriverLike>,
): Map<string, LiveGapResult> {
  const result = new Map<string, LiveGapResult>()

  if (!posData || classification.length === 0) {
    return result
  }

  // Compute per-driver lap time in seconds; fall back to peloton median
  const lapTimesS = classification
    .map((id) => drivers[id]?.last_lap_ms)
    .filter((v): v is number => v !== null && v !== undefined && v > 0)
    .map((v) => v / 1000)

  const medianRawS = median(lapTimesS)
  const medianLapS = Number.isNaN(medianRawS) ? DEFAULT_LAP_MS / 1000 : medianRawS

  // Compute fractional positions for all on-track drivers
  // Each driver's lap time is used to determine frames-per-lap for their fraction
  const fracs = new Map<string, number>()
  for (const id of classification) {
    const d = drivers[id]
    if (!d || d.in_pit || d.retired) continue
    const lapMs = d.last_lap_ms !== null && d.last_lap_ms > 0
      ? d.last_lap_ms
      : medianLapS * 1000
    const frac = interpolateFraction(posData, id, atMs, lapMs)
    if (frac !== null) {
      fracs.set(id, frac)
    }
  }

  // Leader fraction
  const leaderId = classification[0]
  const leaderFrac = fracs.get(leaderId)

  for (let i = 0; i < classification.length; i++) {
    const id = classification[i]
    const d = drivers[id]

    if (!d) continue

    // Skip in-pit or retired — use official values
    if (d.in_pit || d.retired) {
      result.set(id, { gap_s: d.gap_s, interval_s: d.interval_s, fromTelemetry: false })
      continue
    }

    // Leader
    if (i === 0) {
      result.set(id, { gap_s: 0, interval_s: null, fromTelemetry: false })
      continue
    }

    const selfFrac = fracs.get(id)
    if (selfFrac === null || selfFrac === undefined || leaderFrac === undefined) {
      result.set(id, { gap_s: d.gap_s, interval_s: d.interval_s, fromTelemetry: false })
      continue
    }

    const lapS = d.last_lap_ms !== null && d.last_lap_ms > 0
      ? d.last_lap_ms / 1000
      : medianLapS

    // Gap estimate: fraction behind leader * lap time
    const fracBehindLeader = ((leaderFrac - selfFrac + 1) % 1)
    const estGap = fracBehindLeader * lapS

    // Sanity check against official
    const officialGap = d.gap_s
    if (officialGap !== null && Math.abs(estGap - officialGap) > SANITY_THRESHOLD_S) {
      // Lapped car or large discrepancy — use official
      result.set(id, { gap_s: officialGap, interval_s: d.interval_s, fromTelemetry: false })
      continue
    }

    // Interval estimate: gap to car directly ahead
    const aheadId = classification[i - 1]
    const aheadFrac = fracs.get(aheadId)
    let estInterval: number | null = null
    if (aheadFrac !== undefined && aheadFrac !== null) {
      const aheadD = drivers[aheadId]
      const aheadLapS = aheadD?.last_lap_ms !== null && aheadD?.last_lap_ms !== undefined && aheadD.last_lap_ms > 0
        ? aheadD.last_lap_ms / 1000
        : medianLapS
      const fracBehindAhead = ((aheadFrac - selfFrac + 1) % 1)
      estInterval = fracBehindAhead * aheadLapS
      // Sanity check interval
      const officialInt = d.interval_s
      if (officialInt !== null && Math.abs(estInterval - officialInt) > SANITY_THRESHOLD_S) {
        estInterval = officialInt
      }
    } else {
      estInterval = d.interval_s
    }

    result.set(id, {
      gap_s: estGap,
      interval_s: estInterval,
      fromTelemetry: true,
    })
  }

  // Sanity guard: if all telemetry gaps are suspiciously near zero but official
  // gaps are substantial, the telemetry fractions are degenerate — fall back entirely.
  {
    const telEntries = classification.slice(1).map((id) => {
      const r = result.get(id)
      const off = drivers[id]?.gap_s
      return { r, off }
    }).filter(({ r }) => r?.fromTelemetry)

    if (telEntries.length > 0) {
      const allNearZero = telEntries.every(({ r }) => (r?.gap_s ?? 0) < DEGENERATE_GAP_S)
      const anyOfficialLarge = telEntries.some(({ off }) => off !== null && off !== undefined && off > SUBSTANTIAL_GAP_S)
      if (allNearZero && anyOfficialLarge) {
        console.warn('[liveGaps] telemetry degenerate (all gaps ~0, official >1s) — falling back to official')
        for (const id of classification) {
          const d = drivers[id]
          if (!d) continue
          const existing = result.get(id)
          if (existing?.fromTelemetry) {
            result.set(id, { gap_s: d.gap_s, interval_s: d.interval_s, fromTelemetry: false })
          }
        }
      }
    }
  }

  return result
}
