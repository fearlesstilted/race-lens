/**
 * Pure geometry helpers for the track map: SVG path construction, position
 * interpolation from telemetry frames, median lap time, and start/finish line.
 */
import type { PositionsData } from './liveGaps'
import { DEFAULT_LAP_MS } from './liveGaps'

/** Smooth short forward-filled telemetry gaps; longer gaps may be a genuinely stopped car. */
const MAX_INTERPOLATION_GAP_TICKS = 10

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
  if (i0 >= frames.length) return frames[frames.length - 1]
  const point = frames[i0]
  if (point === null) return null

  // FastF1 positions are commonly forward-filled for a few ticks. Treat that
  // short repeated run as one sparse sample instead of holding, then jumping.
  let segmentStart = i0
  while (
    segmentStart > 0 &&
    frames[segmentStart - 1]?.[0] === point[0] &&
    frames[segmentStart - 1]?.[1] === point[1]
  ) {
    segmentStart -= 1
  }

  const maxEnd = Math.min(frames.length - 1, segmentStart + MAX_INTERPOLATION_GAP_TICKS)
  let segmentEnd = segmentStart + 1
  while (
    segmentEnd <= maxEnd &&
    (frames[segmentEnd] === null ||
      (frames[segmentEnd]?.[0] === point[0] && frames[segmentEnd]?.[1] === point[1]))
  ) {
    segmentEnd += 1
  }

  if (segmentEnd > maxEnd) return point
  const nextPoint = frames[segmentEnd]
  if (nextPoint === null) return point
  const alpha = Math.min(Math.max((fi - segmentStart) / (segmentEnd - segmentStart), 0), 1)
  return [
    Math.round((point[0] + alpha * (nextPoint[0] - point[0])) * 10) / 10,
    Math.round((point[1] + alpha * (nextPoint[1] - point[1])) * 10) / 10,
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
