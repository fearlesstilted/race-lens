import React, { useEffect, useRef, useState } from 'react'
import type { TrackData } from '../../api/client'
import { getTrack } from '../../api/client'
import type { DriverState } from '../../api/types'
import { teamColor } from './teamColors'

type Props = {
  sessionId: string | null
  atMs: number
  playing: boolean
  /** Wall-clock ms between stream frames — used to set CSS transition duration. */
  frameMs: number
  drivers: Record<string, DriverState>
  classification: string[]
  sessionStatus?: string
}

// Pit lane: a horizontal row below the map bottom edge
const PIT_LANE_Y = 370
const PIT_LANE_X_START = 30
const PIT_LANE_SPACING = 22

// Smoothing time constant in ms — how fast current_frac catches up to target_frac
const TAU_MS = 300

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
  sessionId, atMs, playing, drivers, classification, sessionStatus,
}: Props) {
  const pathRef = useRef<SVGPathElement>(null)
  const [trackData, setTrackData] = useState<TrackData | null>(null)
  const [trackError, setTrackError] = useState(false)

  // Per-car current fraction (animated) and target fraction (latest computed)
  const currentFracRef = useRef<Map<string, number>>(new Map())
  const targetFracRef = useRef<Map<string, number>>(new Map())

  // Refs to SVG <g> elements for imperative position updates
  const carGroupRefs = useRef<Map<string, SVGGElement>>(new Map())

  // rAF loop handle
  const rafRef = useRef<number | null>(null)
  const lastTimestampRef = useRef<number | null>(null)

  // Track whether we are playing — used inside rAF closure
  const playingRef = useRef(playing)
  useEffect(() => { playingRef.current = playing }, [playing])

  // Fetch track data whenever session changes
  useEffect(() => {
    if (!sessionId) return
    setTrackData(null)
    setTrackError(false)
    getTrack(sessionId)
      .then((d) => setTrackData(d))
      .catch(() => setTrackError(true))
  }, [sessionId])

  // Update target fractions whenever atMs / drivers / classification change
  useEffect(() => {
    const newTargets = computeTargetFractions(atMs, drivers, classification)
    targetFracRef.current = newTargets

    if (!playing) {
      // Scrub: snap current to target immediately, then render one frame
      for (const [id, frac] of newTargets) {
        currentFracRef.current.set(id, frac)
      }
      renderPositions()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atMs, drivers, classification])

  // Render current positions imperatively via SVG element refs
  function renderPositions() {
    const path = pathRef.current
    if (!path) return
    const totalLength = path.getTotalLength()

    for (const [driverId, groupEl] of carGroupRefs.current) {
      const frac = currentFracRef.current.get(driverId)
      if (frac === undefined) continue
      const pt = path.getPointAtLength(frac * totalLength)
      groupEl.setAttribute('transform', `translate(${pt.x.toFixed(2)},${pt.y.toFixed(2)})`)
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

    function tick(timestamp: number) {
      const dt = lastTimestampRef.current !== null ? timestamp - lastTimestampRef.current : 16
      lastTimestampRef.current = timestamp

      const k = 1 - Math.exp(-dt / TAU_MS)

      for (const [id, target] of targetFracRef.current) {
        const current = currentFracRef.current.get(id) ?? target
        // forward-only delta on the circular track
        let delta = ((target - current) % 1 + 1) % 1
        let next: number
        if (delta > 0.5) {
          // Overtake detected (large backward jump) — snap
          next = target
        } else {
          next = (current + delta * k) % 1
        }
        currentFracRef.current.set(id, next)
      }

      renderPositions()

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
            return (
              <g
                key={driverId}
                ref={(el) => {
                  if (el) carGroupRefs.current.set(driverId, el)
                  else carGroupRefs.current.delete(driverId)
                }}
                transform="translate(0,0)"
              >
                <circle
                  r={7}
                  fill={color}
                  stroke={isTop3 ? '#fff' : 'none'}
                  strokeWidth={isTop3 ? 1.5 : 0}
                />
                {isTop3 && (
                  <text
                    x={0}
                    y={-11}
                    textAnchor="middle"
                    fill="#fff"
                    fontSize={12}
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

      <span className="note">TELEMETRY · INTERPOLATED</span>
    </div>
  )
})
