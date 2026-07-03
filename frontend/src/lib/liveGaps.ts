/**
 * Positions telemetry data shape — used by the track map for continuous
 * position interpolation between server ticks.
 */

export type PositionsData = {
  session_id: string
  start_ms: number
  tick_ms: number
  viewbox: [number, number]
  drivers: Record<string, ([number, number] | null)[]>
  /** Per-tick cumulative track progress (laps + arc fraction) for tower ordering. */
  progress?: Record<string, (number | null)[]>
}

/** Fallback lap time used when no telemetry lap times are available (78s ≈ a typical F1 lap). */
export const DEFAULT_LAP_MS = 78000
