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

function median(values: number[]): number {
  if (values.length === 0) return 78
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

/**
 * Interpolate fractional position [0, 1] for a driver at atMs.
 * Returns null if no telemetry or null frame.
 *
 * The fraction is a synthetic value derived from the frame index so that
 * we can compare positions across cars consistently. We map each non-null
 * frame to a fraction = frameIndex / totalFrames.
 */
function interpolateFraction(
  posData: PositionsData,
  driverId: string,
  atMs: number,
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

  // Fraction based on raw frame index / total frames (position on path)
  // We just use fi normalised — each frame advances 1/N of a lap
  const totalFrames = frames.length
  const alpha = fi - i0

  // Find the next valid frame for interpolation
  const i1 = i0 + 1
  const frac0 = i0 / totalFrames
  const frac1 = i1 / totalFrames

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

  const medianLapS = median(lapTimesS)

  // Compute fractional positions for all on-track drivers
  const fracs = new Map<string, number>()
  for (const id of classification) {
    const d = drivers[id]
    if (!d || d.in_pit || d.retired) continue
    const frac = interpolateFraction(posData, id, atMs)
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

    // Driver's own lap time in seconds
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

  // Console log: compare est vs official for P2 (first car with a gap)
  const p2id = classification[1]
  if (p2id && result.has(p2id)) {
    const est = result.get(p2id)!
    const off = drivers[p2id]?.gap_s
    if (est.fromTelemetry && off !== null && off !== undefined) {
      console.debug(
        `[liveGaps] ${p2id} est=${est.gap_s?.toFixed(2)}s official=${off.toFixed(2)}s diff=${Math.abs((est.gap_s ?? 0) - off).toFixed(2)}s`
      )
    }
  }

  return result
}
