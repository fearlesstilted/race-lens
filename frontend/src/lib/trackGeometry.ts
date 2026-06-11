/**
 * Pure geometry helpers for the track map: SVG path construction, position
 * interpolation from telemetry frames, median lap time, and start/finish line.
 */
import type { PositionsData } from './liveGaps'
import { DEFAULT_LAP_MS } from './liveGaps'

/** Interpolate a real position from positions data at atMs.
 * Returns null if no data or null frame. */
export function interpolateRealPos(
  posData: PositionsData,
  driver: string,
  atMs: number,
): [number, number] | null {
  const frames = posData.drivers[driver]
  if (!frames || frames.length === 0) return null
  const tick = posData.tick_ms
  const start = posData.start_ms
  const relMs = atMs - start
  if (relMs < 0) return null
  const fi = relMs / tick
  const i0 = Math.floor(fi)
  const i1 = Math.ceil(fi)
  if (i0 >= frames.length) return frames[frames.length - 1]
  const f0 = frames[i0]
  if (f0 === null) return null
  if (i0 === i1 || i1 >= frames.length) return f0
  const f1 = frames[i1]
  if (f1 === null) return f0
  const alpha = fi - i0
  return [
    Math.round((f0[0] + alpha * (f1[0] - f0[0])) * 10) / 10,
    Math.round((f0[1] + alpha * (f1[1] - f0[1])) * 10) / 10,
  ]
}

export function median(values: number[]): number {
  if (values.length === 0) return DEFAULT_LAP_MS
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

export function buildPathD(points: [number, number][]): string {
  if (points.length === 0) return ''
  const [x0, y0] = points[0]
  const rest = points.slice(1).map(([x, y]) => `L ${x} ${y}`).join(' ')
  return `M ${x0} ${y0} ${rest} Z`
}

/** Endpoints of the perpendicular start/finish line at points[0], or null. */
export function startFinishLine(
  points: [number, number][],
  halfLen = 10,
): { x1: number; y1: number; x2: number; y2: number } | null {
  if (points.length < 2) return null
  const [x0, y0] = points[0]
  const [x1, y1] = points[1]
  const dx = x1 - x0
  const dy = y1 - y0
  const len = Math.sqrt(dx * dx + dy * dy) || 1
  const px = -dy / len
  const py = dx / len
  return {
    x1: x0 + px * halfLen,
    y1: y0 + py * halfLen,
    x2: x0 - px * halfLen,
    y2: y0 - py * halfLen,
  }
}
