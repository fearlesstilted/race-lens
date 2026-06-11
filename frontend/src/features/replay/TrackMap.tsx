import React, { useEffect, useRef, useState } from 'react'
import type { DriverState } from '../../api/types'
import { teamColor } from './teamColors'

// Monaco circuit — hand-drawn clockwise path, viewBox 600×400
// Start/finish: bottom-left straight (harbour front)
// → Sainte Devote (right) → climb to Casino → Mirabeau → Loews hairpin (180°)
// → Portier → tunnel arc → chicane (zigzag) → Tabac → Swimming pool (double S)
// → Rascasse → back to start
const TRACK_PATH =
  // Start/finish straight (harbour)
  'M 60 310 L 180 310 ' +
  // Sainte Devote — sharp right
  'C 210 310 230 295 230 270 ' +
  // Climb Beau Rivage — sweeping left
  'C 230 240 215 215 200 195 ' +
  // Massenet curve
  'C 185 175 175 160 180 140 ' +
  // Casino square — right turn
  'C 185 120 210 108 240 108 ' +
  // Mirabeau Haut — right
  'C 270 108 295 115 310 132 ' +
  // Mirabeau Bas into Loews — tightening
  'C 325 150 328 168 318 185 ' +
  // Loews HAIRPIN — tight 180° loop
  'C 310 202 296 214 278 216 C 260 218 246 210 240 196 ' +
  // Portier — right
  'C 234 183 230 168 235 150 C 240 132 255 122 272 118 ' +
  // Exit Portier, into tunnel — long right arc
  'C 290 114 318 118 340 130 C 362 142 390 162 410 185 ' +
  // Tunnel exit — fast kink
  'C 425 200 435 210 432 226 ' +
  // Nouvelle chicane — sharp left-right
  'C 429 238 418 242 405 238 C 392 234 385 242 388 255 ' +
  // Tabac — gentle right
  'C 392 268 400 278 415 282 ' +
  // Swimming pool S1 — left
  'C 428 286 440 278 444 266 ' +
  // Swimming pool S2 — right
  'C 448 254 456 244 468 242 C 480 240 490 248 490 260 ' +
  // Rascasse — right hairpin
  'C 490 275 480 292 460 300 C 440 308 400 312 350 312 ' +
  // Anthony Noghes — back to start straight
  'C 300 312 260 312 180 310'

// Sector 1 highlight: start line → Sainte Devote → up to Casino
const SECTOR1_PATH =
  'M 60 310 L 180 310 C 210 310 230 295 230 270 C 230 240 215 215 200 195 C 185 175 175 160 180 140 C 185 120 210 108 240 108'

type Props = {
  atMs: number
  playing: boolean
  drivers: Record<string, DriverState>
  classification: string[]
  sessionStatus?: string
}

type CarPos = { x: number; y: number }

// Pit lane: a horizontal row below the start straight
const PIT_LANE_Y = 340
const PIT_LANE_X_START = 60
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

export const TrackMap = React.memo(function TrackMap({ atMs, playing, drivers, classification, sessionStatus }: Props) {
  const pathRef = useRef<SVGPathElement>(null)
  const [positions, setPositions] = useState<Record<string, CarPos>>({})

  useEffect(() => {
    const path = pathRef.current
    if (!path) return

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

    // Find last known gap among on-track drivers
    // Drivers with gap_s=null and not position 1: distribute behind the last known driver
    const knownGap: string[] = []
    const unknownGap: string[] = []
    for (const id of onTrack) {
      const d = drivers[id]
      if (!d) continue
      if (d.position === 1 || d.gap_s !== null) knownGap.push(id)
      else unknownGap.push(id)
    }

    // Spread for fallback: use 1s per position behind the last known
    const lastKnownGap = knownGap.length > 0
      ? (drivers[knownGap[knownGap.length - 1]]?.gap_s ?? 0)
      : 0
    const fallbackSpacingFrac = (1000) / avgLapMs // 1 second apart

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
        // fallback: position after last known, spaced 1s apart
        const unknownIdx = unknownGap.indexOf(driverId)
        const baseGap = lastKnownGap * 1000
        gapFrac = (baseGap + (unknownIdx + 1) * 1000) / avgLapMs
      }

      const frac = ((leaderFrac - gapFrac) % 1 + 1) % 1
      const point = path.getPointAtLength(frac * totalLength)
      newPositions[driverId] = { x: point.x, y: point.y }
    }

    // In-pit: row below start straight
    for (let i = 0; i < inPit.length; i++) {
      const id = inPit[i]
      newPositions[id] = {
        x: PIT_LANE_X_START + i * PIT_LANE_SPACING,
        y: PIT_LANE_Y,
      }
    }

    setPositions(newPositions)
  }, [atMs, drivers, classification])

  const watermark = statusWatermark(sessionStatus ?? '')
  const top3 = classification.slice(0, 3)

  return (
    <div className="map">
      <svg width="600" height="400" viewBox="0 0 600 400" fill="none">
        {/* Track base */}
        <path
          d={TRACK_PATH}
          stroke="#26262e"
          strokeWidth="14"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        {/* Sector 1 highlight (leader sector) */}
        <path
          d={SECTOR1_PATH}
          stroke="#3d3d49"
          strokeWidth="14"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        {/* Measurement path (invisible) */}
        <path
          ref={pathRef}
          d={TRACK_PATH}
          stroke="none"
          fill="none"
        />

        {/* Pit lane indicator line */}
        <line
          x1={PIT_LANE_X_START - 8}
          y1={PIT_LANE_Y}
          x2={PIT_LANE_X_START + classification.filter(id => drivers[id]?.in_pit).length * PIT_LANE_SPACING + 8}
          y2={PIT_LANE_Y}
          stroke="#f2a90044"
          strokeWidth="1"
        />

        {/* Status watermark */}
        {watermark && (
          <text
            x={300}
            y={200}
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
        {classification.map((driverId, idx) => {
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

      <span className="note">SCHEMATIC · INTERPOLATED</span>
    </div>
  )
})
