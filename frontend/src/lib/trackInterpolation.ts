export type TrackPoint = [number, number]

const MAX_PROGRESS_PER_TICK = 0.12

function interpolateProgress(
  frames: (number | null)[],
  frameIndex: number,
): number | null {
  if (frameIndex < 0 || frames.length === 0) return null
  const before = Math.floor(frameIndex)
  if (before >= frames.length) return frames[frames.length - 1]
  const current = frames[before]
  if (current === null) return null
  const previous = frames[before - 1]
  if (
    previous !== undefined &&
    previous !== null &&
    (current < previous || current - previous > MAX_PROGRESS_PER_TICK)
  ) return null
  const next = frames[before + 1]
  if (next === undefined || next === null) return current
  if (next < current || next - current > MAX_PROGRESS_PER_TICK) return null
  return current + (next - current) * (frameIndex - before)
}

export function progressPathPosition(
  frames: (number | null)[],
  path: TrackPoint[],
  frameIndex: number,
): TrackPoint | null {
  const progress = interpolateProgress(frames, frameIndex)
  if (progress === null || path.length === 0) return null
  const pathIndex = (((progress % 1) + 1) % 1) * path.length
  const before = Math.floor(pathIndex) % path.length
  const after = (before + 1) % path.length
  const ratio = pathIndex - Math.floor(pathIndex)
  return [
    path[before][0] + (path[after][0] - path[before][0]) * ratio,
    path[before][1] + (path[after][1] - path[before][1]) * ratio,
  ]
}
