import React, { useEffect, useRef, useState } from 'react'
import type { TrackData } from '../../api/client'
import { getTrack } from '../../api/client'
import type { DriverState } from '../../api/types'
import { teamColor } from './teamColors'

type Props = {
  sessionId: string | null
  atMs: number
  playing: boolean
  drivers: Record<string, DriverState>
  classification: string[]
  sessionStatus?: string
}

type CarPos = { x: number; y: number }

// Pit lane: a horizontal row below the map bottom edge
const PIT_LANE_Y = 370
const PIT_LANE_X_START = 30
const PIT_LANE_SPACING = 22

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

export const TrackMap = React.memo(function TrackMap({
  sessionId, atMs, playing, drivers, classification, sessionStatus,
}: Props) {
  const pathRef = useRef<SVGPathElement>(null)
  const [positions, setPositions] = useState<Record<string, CarPos>>({})
  const [trackData, setTrackData] = useState<TrackData | null>(null)
  const [trackError, setTrackError] = useState(false)

  // Fetch track data whenever session changes
  useEffect(() => {
    if (!sessionId) return
    setTrackData(null)
    setTrackError(false)
    getTrack(sessionId)
      .then((d) => setTrackData(d))
      .catch(() => setTrackError(true))
  }, [sessionId])

  useEffect(() => {
    const path = pathRef.current
    if (!path || !trackData) return

    const totalLength = path.getTotalLength()

    // Avg lap time from the peloton (ignore null)
    const lapTimes = classification
      .map((id) => drivers[id]?.last_lap_ms)
      .filter((v): v is number => v !== null && v !== undefined && v > 0)
    const avgLapMs = median(lapTimes)

    // Leader fraction
    const leaderFrac = (atMs % avgLapMs) / avgLapMs

    // Separate on-track and in-pit
    const onTrack: string[] = []
    const inPit: string[] = []
    for (const id of classification) {
      if (drivers[id]?.in_pit) inPit.push(id)
      else onTrack.push(id)
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

    const newPositions: Record<string, CarPos> = {}

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
      const point = path.getPointAtLength(frac * totalLength)
      newPositions[driverId] = { x: point.x, y: point.y }
    }

    // In-pit: row below map
    for (let i = 0; i < inPit.length; i++) {
      const id = inPit[i]
      newPositions[id] = {
        x: PIT_LANE_X_START + i * PIT_LANE_SPACING,
        y: PIT_LANE_Y,
      }
    }

    setPositions(newPositions)
  }, [atMs, drivers, classification, trackData])

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
          x2={PIT_LANE_X_START + classification.filter(id => drivers[id]?.in_pit).length * PIT_LANE_SPACING + 8}
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

        {/* Cars */}
        {classification.map((driverId) => {
          const pos = positions[driverId]
          if (!pos) return null
          const color = teamColor(driverId)
          const isTop3 = top3.includes(driverId)
          const isInPit = drivers[driverId]?.in_pit
          return (
            <g
              key={driverId}
              transform={`translate(${pos.x},${pos.y})`}
              style={playing && !isInPit ? { transition: 'transform 0.8s linear' } : undefined}
            >
              <circle
                r={isInPit ? 5 : 7}
                fill={color}
                opacity={isInPit ? 0.6 : 1}
                stroke={isTop3 && !isInPit ? '#fff' : 'none'}
                strokeWidth={isTop3 && !isInPit ? 1.5 : 0}
              />
              {isTop3 && !isInPit && (
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
      </svg>

      <span className="note">TELEMETRY · INTERPOLATED</span>
    </div>
  )
})
