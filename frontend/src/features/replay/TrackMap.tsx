import React, { useEffect, useRef, useState } from 'react'
import type { TrackData } from '../../api/client'
import { getTrack } from '../../api/client'
import type { DriverState } from '../../api/types'
import { teamColor } from './teamColors'

// ── Real-telemetry positions data ────────────────────────────────────────────

type PositionsData = {
  session_id: string
  start_ms: number
  tick_ms: number
  viewbox: [number, number]
  drivers: Record<string, ([number, number] | null)[]>
}

async function fetchPositions(sessionId: string): Promise<PositionsData | null> {
  const res = await fetch(`/api/sessions/${sessionId}/positions`)
  if (!res.ok) return null
  return res.json()
}

/** Interpolate a real position from positions data at atMs.
 * Returns null if no data or null frame. */
function interpolateRealPos(
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

type Props = {
  sessionId: string | null
  atMs: number
  playing: boolean
  /** Wall-clock ms between stream frames — used to set CSS transition duration. */
  frameMs: number
  playbackSpeed: number
  drivers: Record<string, DriverState>
  classification: string[]
  sessionStatus?: string
  selectedIds?: string[]
}

// Pit lane: a horizontal row below the map bottom edge
const PIT_LANE_Y = 370
const PIT_LANE_X_START = 30
const PIT_LANE_SPACING = 22

// Correction smoothing tau in ms — how fast current_frac catches up to target_frac
const CORRECTION_TAU_MS = 2000

function median(values: number[]): number {
  if (values.length === 0) return 78000
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

function statusWatermark(status: string): string | null {
  if (status === 'red_flag') return 'RED FLAG'
  if (status === 'safety_car') return 'SAFETY CAR'
  if (status === 'virtual_safety_car' || status === 'vsc') return 'VIRTUAL SC'
  return null
}

function buildPathD(points: [number, number][]): string {
  if (points.length === 0) return ''
  const [x0, y0] = points[0]
  const rest = points.slice(1).map(([x, y]) => `L ${x} ${y}`).join(' ')
  return `M ${x0} ${y0} ${rest} Z`
}

/** Compute target fractions for all on-track drivers. Returns a map driverId → frac (0..1). */
function computeTargetFractions(
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

export const TrackMap = React.memo(function TrackMap({
  sessionId, atMs, playing, playbackSpeed, drivers, classification, sessionStatus, selectedIds = [],
}: Props) {
  const pathRef = useRef<SVGPathElement>(null)
  const [trackData, setTrackData] = useState<TrackData | null>(null)
  const [trackError, setTrackError] = useState(false)
  const [positionsData, setPositionsData] = useState<PositionsData | null>(null)

  // Per-car current fraction (animated) and target fraction (latest computed)
  const currentFracRef = useRef<Map<string, number>>(new Map())
  const targetFracRef = useRef<Map<string, number>>(new Map())

  // Refs to SVG <g> elements for imperative position updates
  const carGroupRefs = useRef<Map<string, SVGGElement>>(new Map())

  // rAF loop handle
  const rafRef = useRef<number | null>(null)
  const lastTimestampRef = useRef<number | null>(null)

  // Local session clock for real-telemetry rAF (ms) — advanced by wall*speed
  const localAtMsRef = useRef<number>(0)

  // Track whether we are playing — used inside rAF closure
  const playingRef = useRef(playing)
  useEffect(() => { playingRef.current = playing }, [playing])

  // Refs for values used inside rAF closure
  const playbackSpeedRef = useRef(playbackSpeed)
  useEffect(() => { playbackSpeedRef.current = playbackSpeed }, [playbackSpeed])

  const sessionStatusRef = useRef(sessionStatus ?? '')
  useEffect(() => { sessionStatusRef.current = sessionStatus ?? '' }, [sessionStatus])

  // Per-driver estimated lap ms (for dead reckoning)
  const driverLapMsRef = useRef<Map<string, number>>(new Map())

  // Peloton median fallback — updated on each drivers change
  const pelotonMedianRef = useRef<number>(78000)

  // Ref for positionsData used inside rAF closure
  const positionsDataRef = useRef<PositionsData | null>(null)
  useEffect(() => { positionsDataRef.current = positionsData }, [positionsData])

  // Ref for atMs used inside rAF closure (real-telemetry mode)
  const atMsRef = useRef(atMs)
  useEffect(() => { atMsRef.current = atMs }, [atMs])

  // Fetch track data and positions data whenever session changes
  useEffect(() => {
    if (!sessionId) return
    setTrackData(null)
    setTrackError(false)
    setPositionsData(null)
    getTrack(sessionId)
      .then((d) => setTrackData(d))
      .catch(() => setTrackError(true))
    fetchPositions(sessionId)
      .then((d) => setPositionsData(d))
      .catch(() => setPositionsData(null))
  }, [sessionId])

  // Update target fractions whenever atMs / drivers / classification change
  useEffect(() => {
    const newTargets = computeTargetFractions(atMs, drivers, classification)
    targetFracRef.current = newTargets

    // Update per-driver lap ms estimates and peloton median
    const lapTimes: number[] = []
    for (const id of classification) {
      const d = drivers[id]
      if (!d) continue
      if (d.last_lap_ms && d.last_lap_ms > 0) {
        driverLapMsRef.current.set(id, d.last_lap_ms)
        lapTimes.push(d.last_lap_ms)
      }
    }
    if (lapTimes.length > 0) {
      pelotonMedianRef.current = median(lapTimes)
    }

    if (!playing) {
      if (positionsDataRef.current) {
        // Real-telemetry scrub: render at atMs directly
        renderPositions(atMs)
      } else {
        // Schematic scrub: snap fractions, render via path
        for (const [id, frac] of newTargets) {
          currentFracRef.current.set(id, frac)
        }
        renderPositions()
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atMs, drivers, classification])

  // Render current positions imperatively via SVG element refs.
  // Real-telemetry mode: uses positionsDataRef + localAtMsRef to get XY directly.
  // Fallback (schematic) mode: uses currentFracRef + SVG path.
  function renderPositions(overrideAtMs?: number) {
    const posData = positionsDataRef.current
    if (posData) {
      // REAL TELEMETRY MODE
      const queryMs = overrideAtMs ?? localAtMsRef.current
      for (const [driverId, groupEl] of carGroupRefs.current) {
        const xy = interpolateRealPos(posData, driverId, queryMs)
        if (xy === null) {
          // null frame — hide car
          groupEl.setAttribute('visibility', 'hidden')
        } else {
          groupEl.setAttribute('visibility', 'visible')
          groupEl.setAttribute('transform', `translate(${xy[0]},${xy[1]})`)
        }
      }
    } else {
      // SCHEMATIC FALLBACK MODE
      const path = pathRef.current
      if (!path) return
      const totalLength = path.getTotalLength()
      for (const [driverId, groupEl] of carGroupRefs.current) {
        groupEl.setAttribute('visibility', 'visible')
        const frac = currentFracRef.current.get(driverId)
        if (frac === undefined) continue
        const pt = path.getPointAtLength(frac * totalLength)
        groupEl.setAttribute('transform', `translate(${pt.x.toFixed(2)},${pt.y.toFixed(2)})`)
      }
    }
  }

  // rAF loop — only active while playing
  useEffect(() => {
    if (!playing) {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      lastTimestampRef.current = null
      return
    }

    // Sync local session clock to current atMs when starting playback
    localAtMsRef.current = atMsRef.current

    function tick(timestamp: number) {
      const dt = lastTimestampRef.current !== null ? timestamp - lastTimestampRef.current : 16
      lastTimestampRef.current = timestamp

      const speed = playbackSpeedRef.current

      if (positionsDataRef.current) {
        // REAL TELEMETRY MODE: advance local session clock and render
        localAtMsRef.current += dt * speed
        renderPositions()
      } else {
        // SCHEMATIC FALLBACK: dead reckoning + soft correction toward target fracs

        // Dead reckoning speed multiplier based on session status
        const status = sessionStatusRef.current
        let drMultiplier = 1
        if (status === 'red_flag') drMultiplier = 0
        else if (status === 'safety_car' || status === 'virtual_safety_car' || status === 'vsc') drMultiplier = 0.6

        const pelotonMs = pelotonMedianRef.current

        for (const [id, target] of targetFracRef.current) {
          const current = currentFracRef.current.get(id) ?? target

          // --- Dead reckoning: advance car by wall-time * speed / lap_ms
          const lapMs = driverLapMsRef.current.get(id) ?? pelotonMs
          const drDelta = (dt * speed * drMultiplier) / lapMs
          const afterDR = (current + drDelta) % 1

          // --- Soft correction toward target (circular, shortest path)
          let corrDelta = ((target - afterDR) % 1 + 1) % 1
          if (corrDelta > 0.5) corrDelta -= 1 // allow backward correction
          let next: number
          if (Math.abs(corrDelta) > 0.5) {
            // Large snap (position data jump > half lap) — snap immediately
            next = target
          } else {
            const corrK = 1 - Math.exp(-dt / CORRECTION_TAU_MS)
            next = ((afterDR + corrDelta * corrK) % 1 + 1) % 1
          }
          currentFracRef.current.set(id, next)
        }

        renderPositions()
      }

      if (playingRef.current) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      lastTimestampRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing])

  // Register/unregister car group refs as classification set changes
  // (cleanup stale entries)
  useEffect(() => {
    const ids = new Set(classification)
    for (const id of carGroupRefs.current.keys()) {
      if (!ids.has(id)) {
        carGroupRefs.current.delete(id)
        currentFracRef.current.delete(id)
      }
    }
  }, [classification])

  const watermark = statusWatermark(sessionStatus ?? '')
  const top3 = classification.slice(0, 3)
  const hasFocus = selectedIds.length > 0

  const [vw, vh] = trackData?.viewbox ?? [600, 400]
  const pathD = trackData ? buildPathD(trackData.points) : ''

  // Start/finish line: perpendicular short stroke at points[0]
  let sfLine: React.ReactNode = null
  if (trackData && trackData.points.length >= 2) {
    const [x0, y0] = trackData.points[0]
    const [x1, y1] = trackData.points[1]
    const dx = x1 - x0
    const dy = y1 - y0
    const len = Math.sqrt(dx * dx + dy * dy) || 1
    // perpendicular direction
    const px = -dy / len
    const py = dx / len
    const halfLen = 10
    sfLine = (
      <line
        x1={x0 + px * halfLen}
        y1={y0 + py * halfLen}
        x2={x0 - px * halfLen}
        y2={y0 - py * halfLen}
        stroke="#ffffff"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    )
  }

  // Pit positions computed once per render (static — no animation needed)
  const pitDrivers = classification.filter(id => drivers[id]?.in_pit)

  return (
    <div className="map">
      <svg width={vw} height={vh} viewBox={`0 0 ${vw} ${vh}`} fill="none">
        {trackError && (
          <text
            x={vw / 2}
            y={vh / 2}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#55555f"
            fontSize={16}
            fontFamily="'Barlow Condensed', sans-serif"
            letterSpacing="0.2em"
          >
            NO TRACK DATA
          </text>
        )}

        {trackData && (
          <>
            {/* Track base */}
            <path
              d={pathD}
              stroke="#26262e"
              strokeWidth={12}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            {/* Invisible measurement path */}
            <path ref={pathRef} d={pathD} stroke="none" fill="none" />
            {/* Start/finish line */}
            {sfLine}
          </>
        )}

        {/* Pit lane indicator */}
        <line
          x1={PIT_LANE_X_START - 8}
          y1={PIT_LANE_Y}
          x2={PIT_LANE_X_START + pitDrivers.length * PIT_LANE_SPACING + 8}
          y2={PIT_LANE_Y}
          stroke="#f2a90044"
          strokeWidth={1}
        />

        {/* Status watermark */}
        {watermark && (
          <text
            x={vw / 2}
            y={vh / 2}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#ffffff"
            opacity={0.1}
            fontSize={52}
            fontStyle="italic"
            fontWeight={900}
            fontFamily="'Barlow Condensed', sans-serif"
            letterSpacing="0.06em"
          >
            {watermark}
          </text>
        )}

        {/* On-track cars — initial transform is 0,0; rAF loop updates imperatively */}
        {classification
          .filter(id => !drivers[id]?.in_pit && !drivers[id]?.retired)
          .map((driverId) => {
            const color = teamColor(driverId)
            const isTop3 = top3.includes(driverId)
            const isSelected = selectedIds.includes(driverId)
            const isDimmed = hasFocus && !isSelected
            const r = isSelected ? 9 : 7
            const showLabel = isSelected || isTop3
            return (
              <g
                key={driverId}
                ref={(el) => {
                  if (el) carGroupRefs.current.set(driverId, el)
                  else carGroupRefs.current.delete(driverId)
                }}
                transform="translate(0,0)"
                opacity={isDimmed ? 0.5 : 1}
              >
                <circle
                  r={r}
                  fill={color}
                  stroke={isSelected ? '#fff' : isTop3 ? '#fff' : 'none'}
                  strokeWidth={isSelected ? 2 : isTop3 ? 1.5 : 0}
                />
                {showLabel && (
                  <text
                    x={0}
                    y={-13}
                    textAnchor="middle"
                    fill="#fff"
                    fontSize={isSelected ? 13 : 12}
                    fontStyle="italic"
                    fontWeight={700}
                    fontFamily="'Barlow Condensed', sans-serif"
                    letterSpacing="0.04em"
                  >
                    {driverId}
                  </text>
                )}
              </g>
            )
          })}

        {/* Pit lane cars — static row, no animation */}
        {pitDrivers.map((driverId, i) => {
          const color = teamColor(driverId)
          return (
            <g
              key={driverId}
              transform={`translate(${PIT_LANE_X_START + i * PIT_LANE_SPACING},${PIT_LANE_Y})`}
            >
              <circle r={5} fill={color} opacity={0.6} />
            </g>
          )
        })}
      </svg>

      <span className="note">{positionsData ? 'LIVE TELEMETRY' : 'SCHEMATIC · INTERPOLATED'}</span>
    </div>
  )
})
