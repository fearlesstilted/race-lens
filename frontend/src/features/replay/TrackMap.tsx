import React, { useEffect, useRef, useState } from 'react'
import type { DriverState } from '../../api/types'
import { teamColor } from './teamColors'

// Monaco-like schematic path (clockwise, roughly 460×270)
const TRACK_PATH =
  'M70 215 C45 170 55 125 100 103 C145 81 165 45 220 40 C275 35 305 57 340 79 C383 106 415 122 404 166 C393 204 348 198 315 214 C271 236 238 250 183 244 C128 238 92 256 70 215 Z'

type Props = {
  atMs: number
  playing: boolean
  drivers: Record<string, DriverState>
  classification: string[]
}

type CarPos = { x: number; y: number }

function median(values: number[]): number {
  if (values.length === 0) return 78000
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

export function TrackMap({ atMs, playing, drivers, classification }: Props) {
  const pathRef = useRef<SVGPathElement>(null)
  const [positions, setPositions] = useState<Record<string, CarPos>>({})

  useEffect(() => {
    const path = pathRef.current
    if (!path) return

    const totalLength = path.getTotalLength()

    // Compute avg lap time from pelotone
    const lapTimes = classification
      .map((id) => drivers[id]?.last_lap_ms)
      .filter((v): v is number => v !== null && v !== undefined && v > 0)
    const avgLapMs = median(lapTimes)

    // Leader fraction
    const leaderFrac = (atMs % avgLapMs) / avgLapMs

    const newPositions: Record<string, CarPos> = {}

    for (const driverId of classification) {
      const d = drivers[driverId]
      if (!d) continue
      if (d.in_pit) continue
      if (d.gap_s === null && d.position !== 1) continue

      const gapFrac = d.position === 1 ? 0 : (d.gap_s! * 1000) / avgLapMs
      const frac = ((leaderFrac - gapFrac) % 1 + 1) % 1
      const point = path.getPointAtLength(frac * totalLength)
      newPositions[driverId] = { x: point.x, y: point.y }
    }

    setPositions(newPositions)
  }, [atMs, drivers, classification])

  const inPitCount = classification.filter((id) => drivers[id]?.in_pit).length
  const top3 = classification.slice(0, 3)

  return (
    <div className="map">
      <svg width="460" height="270" viewBox="0 0 460 270" fill="none">
        {/* Track outline */}
        <path
          d={TRACK_PATH}
          stroke="#26262e"
          strokeWidth="16"
          strokeLinejoin="round"
        />
        {/* Sector 1 highlight */}
        <path
          d="M70 215 C45 170 55 125 100 103 C145 81 165 45 220 40"
          stroke="#3d3d49"
          strokeWidth="16"
          strokeLinejoin="round"
        />
        {/* Invisible path used only for measurement */}
        <path
          ref={pathRef}
          d={TRACK_PATH}
          stroke="none"
          fill="none"
        />

        {/* Cars */}
        {classification.map((driverId, idx) => {
          const pos = positions[driverId]
          if (!pos) return null
          const color = teamColor(driverId)
          const isTop3 = idx < 3
          return (
            <g key={driverId} style={playing ? { transition: 'transform 0.8s linear' } : undefined}
               transform={`translate(${pos.x},${pos.y})`}>
              <circle
                r={7}
                fill={color}
                stroke={isTop3 ? '#fff' : 'none'}
                strokeWidth={isTop3 ? 1.5 : 0}
                style={playing ? { transition: 'cx 0.8s linear, cy 0.8s linear' } : undefined}
              />
              {isTop3 && (
                <text
                  x={0}
                  y={-10}
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

      {inPitCount > 0 && (
        <span className="map-pit">IN PIT: {inPitCount}</span>
      )}
      <span className="note">SCHEMATIC · INTERPOLATED</span>
    </div>
  )
}
