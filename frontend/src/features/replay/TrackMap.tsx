import React, { useEffect, useState } from 'react'
import type { TrackData } from '../../api/client'
import { getTrack } from '../../api/client'
import type { Battle, DriverState } from '../../api/types'
import type { PositionsData } from '../../lib/liveGaps'
import { buildPathD, startFinishLine } from '../../lib/trackGeometry'
import { teamColor } from './teamColors'
import { useTrackAnimation } from './useTrackAnimation'

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
  /** Session time (ms) when current neutralisation started — for elapsed timer in badge. */
  neutralizationStartMs?: number | null
  selectedIds?: string[]
  /** Positions telemetry data lifted from parent (useReplay). If null, schematic mode is used. */
  positionsData: PositionsData | null
  /** Whether the PROJECTION overlay (ghost cars) is enabled. */
  projection?: boolean
  /** Active battles for on-map highlights */
  battles?: Battle[]
}

/** Advance a fractional lap position forward by ghostSec seconds. */
function advanceGhostFrac(frac: number, ghostSec: number, lapMs: number): number {
  return ((frac + (ghostSec * 1000) / lapMs) % 1 + 1) % 1
}

// Pit lane overlay — fixed position in bottom-left of SVG coordinate space
// These are SVG units, sized relative to typical 600x400 viewbox
const PIT_BOX_X = 10
const PIT_BOX_Y_TOP = 320
const PIT_BOX_HEIGHT = 60
const PIT_BOX_CAR_Y = PIT_BOX_Y_TOP + 38
const PIT_CAR_SPACING = 26

function statusWatermark(status: string): { text: string; color: string } | null {
  if (status === 'red_flag') return { text: 'RED FLAG', color: '#cc0000' }
  if (status === 'safety_car') return { text: 'SAFETY CAR', color: '#f2a900' }
  if (status === 'vsc') return { text: 'VIRTUAL SC', color: '#f2a900' }
  return null
}

function trackStrokeColor(status: string): string {
  if (status === 'safety_car' || status === 'vsc') return '#f2a900'
  if (status === 'red_flag') return '#cc0000'
  return '#26262e'
}

function trackShadow(status: string): string | undefined {
  if (status === 'safety_car' || status === 'vsc')
    return '0 0 18px 6px #f2a900aa'
  if (status === 'red_flag') return '0 0 18px 6px #cc0000aa'
  return undefined
}

/** Format elapsed ms as M:SS */
function fmtElapsed(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Ghost cars: fractional positions +30s ahead, computed each render in schematic mode
const GHOST_AHEAD_S = 30

export const TrackMap = React.memo(function TrackMap({
  sessionId, atMs, playing, playbackSpeed, drivers, classification, sessionStatus, neutralizationStartMs,
  selectedIds = [], positionsData, projection = false, battles = [],
}: Props) {
  const [trackData, setTrackData] = useState<TrackData | null>(null)
  const [trackError, setTrackError] = useState(false)

  const { pathRef, registerCar, currentFracRef, driverLapMsRef, pelotonMedianRef } = useTrackAnimation({
    atMs, playing, playbackSpeed, drivers, classification, sessionStatus, positionsData,
  })

  // Ghost positions for schematic mode — recomputed on atMs change
  const [ghostPositions, setGhostPositions] = useState<Map<string, [number, number]>>(new Map())

  useEffect(() => {
    if (!projection || positionsData) {
      setGhostPositions(new Map())
      return
    }
    const path = pathRef.current
    if (!path) return
    const totalLength = path.getTotalLength()
    const positions = new Map<string, [number, number]>()
    const pelotonMs = pelotonMedianRef.current
    for (const driverId of classification) {
      if (drivers[driverId]?.in_pit || drivers[driverId]?.retired) continue
      const frac = currentFracRef.current.get(driverId)
      if (frac === undefined) continue
      const lapMs = driverLapMsRef.current.get(driverId) ?? pelotonMs
      const ghostFrac = advanceGhostFrac(frac, GHOST_AHEAD_S, lapMs)
      const pt = path.getPointAtLength(ghostFrac * totalLength)
      positions.set(driverId, [pt.x, pt.y])
    }
    setGhostPositions(positions)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atMs, projection, positionsData, classification])

  // Fetch track data whenever session changes
  useEffect(() => {
    if (!sessionId) return
    setTrackData(null)
    setTrackError(false)
    getTrack(sessionId)
      .then((d) => setTrackData(d))
      .catch(() => setTrackError(true))
  }, [sessionId])

  const status = sessionStatus ?? ''
  const watermark = statusWatermark(status)
  const trackStroke = trackStrokeColor(status)
  const trackShadowFilter = trackShadow(status)
  const elapsedTimer = watermark && neutralizationStartMs != null
    ? fmtElapsed(atMs - neutralizationStartMs)
    : null
  const top3 = classification.slice(0, 3)
  const hasFocus = selectedIds.length > 0

  const [vw, vh] = trackData?.viewbox ?? [600, 400]
  const pathD = trackData ? buildPathD(trackData.points) : ''
  const sf = trackData ? startFinishLine(trackData.points) : null

  const pitDrivers = classification.filter(id => drivers[id]?.in_pit)

  // Cars to draw: union of state classification and telemetry drivers, so the
  // formation lap (before any timing events exist) still shows cars from the
  // position telemetry.
  const carIds = positionsData
    ? Array.from(new Set<string>([...classification, ...Object.keys(positionsData.drivers)]))
    : classification

  return (
    <div className="map">
      <svg viewBox={`0 0 ${vw} ${vh}`} preserveAspectRatio="xMidYMid meet" fill="none" style={{ width: '100%', height: '100%' }}>
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
            {trackShadowFilter && (
              <defs>
                <filter id="track-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor={watermark?.color ?? '#f2a900'} floodOpacity="0.7" />
                </filter>
              </defs>
            )}
            {/* Track base */}
            <path
              d={pathD}
              stroke={trackStroke}
              strokeWidth={12}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
              filter={trackShadowFilter ? 'url(#track-glow)' : undefined}
            />
            {/* Invisible measurement path */}
            <path ref={pathRef} d={pathD} stroke="none" fill="none" />
            {/* Start/finish line */}
            {sf && (
              <line
                x1={sf.x1}
                y1={sf.y1}
                x2={sf.x2}
                y2={sf.y2}
                stroke="#ffffff"
                strokeWidth={1.5}
                strokeLinecap="round"
              />
            )}
            {/* Corner numbers */}
            {(trackData.corners ?? []).map((c) => (
              <text
                key={`c${c.number}`}
                x={c.x + 4}
                y={c.y - 4}
                textAnchor="start"
                dominantBaseline="auto"
                fill="#8a8a9a"
                fontSize={9}
                fontFamily="'Barlow Condensed', sans-serif"
                letterSpacing="0"
                pointerEvents="none"
              >
                {c.number}
              </text>
            ))}
          </>
        )}

        {/* Pit lane pocket */}
        {trackData && (
          <g>
            {/* Background rect */}
            <rect
              x={PIT_BOX_X - 6}
              y={PIT_BOX_Y_TOP}
              width={Math.max(80, pitDrivers.length * PIT_CAR_SPACING + 20)}
              height={PIT_BOX_HEIGHT}
              fill="#0c0c0fcc"
              stroke="#f2a90066"
              strokeWidth={1}
              rx={2}
            />
            {/* PIT LANE label */}
            <text
              x={PIT_BOX_X}
              y={PIT_BOX_Y_TOP + 13}
              fill="#f2a900bb"
              fontSize={11}
              fontFamily="'Barlow Condensed', sans-serif"
              fontWeight={700}
              letterSpacing="0.18em"
            >
              PIT LANE
            </text>
            {/* Count badge */}
            {pitDrivers.length > 0 && (
              <text
                x={PIT_BOX_X}
                y={PIT_BOX_Y_TOP + 26}
                fill="#f2a90077"
                fontSize={8}
                fontFamily="'Barlow Condensed', sans-serif"
                fontWeight={600}
                letterSpacing="0.08em"
              >
                {pitDrivers.length} IN PITS
              </text>
            )}
          </g>
        )}

        {/* Status badge — prominent overlay for SC/VSC/red flag */}
        {watermark && (
          <g>
            {/* Badge background pill */}
            <rect
              x={vw / 2 - 96}
              y={vh / 2 - 22}
              width={192}
              height={44}
              rx={6}
              fill={watermark.color}
              opacity={0.92}
            />
            <text
              x={vw / 2}
              y={elapsedTimer ? vh / 2 - 5 : vh / 2}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="#000"
              fontSize={elapsedTimer ? 18 : 22}
              fontStyle="italic"
              fontWeight={900}
              fontFamily="'Barlow Condensed', sans-serif"
              letterSpacing="0.08em"
            >
              {watermark.text}
            </text>
            {elapsedTimer && (
              <text
                x={vw / 2}
                y={vh / 2 + 13}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="#000"
                fontSize={14}
                fontWeight={700}
                fontFamily="'Barlow Condensed', sans-serif"
                letterSpacing="0.04em"
                opacity={0.8}
              >
                {elapsedTimer}
              </text>
            )}
          </g>
        )}

        {/* On-track cars — initial transform is 0,0; rAF loop updates imperatively */}
        {carIds
          .filter(id => !drivers[id]?.in_pit && !drivers[id]?.retired)
          .map((driverId) => {
            const color = teamColor(driverId)
            const isTop3 = top3.includes(driverId)
            const isSelected = selectedIds.includes(driverId)
            const isDimmed = hasFocus && !isSelected
            const r = isSelected ? 9 : 7
            const showLabel = isSelected || isTop3
            const inBattle = battles.some(b => b.chaser_id === driverId || b.leader_id === driverId)
            const compound = drivers[driverId]?.tyre_compound?.charAt(0).toUpperCase() ?? null
            const compoundColor =
              compound === 'S' ? '#ff2d2d' :
              compound === 'M' ? '#ffd900' :
              compound === 'H' ? '#ececec' :
              compound === 'I' ? '#39b54a' :
              compound === 'W' ? '#0067ff' : null
            return (
              <g
                key={driverId}
                ref={registerCar(driverId)}
                transform="translate(0,0)"
                opacity={isDimmed ? 0.5 : 1}
              >
                {/* Battle glow ring */}
                {inBattle && (
                  <circle r={r + 5} fill="none" stroke="#f2a900" strokeWidth={1.2} opacity={0.7} />
                )}
                {/* Compound ring */}
                {compoundColor && !inBattle && (
                  <circle r={r + 3} fill="none" stroke={compoundColor} strokeWidth={1} opacity={0.55} />
                )}
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

        {/* Ghost cars — projection overlay, +30s ahead, schematic mode only */}
        {projection && !positionsData && [...ghostPositions.entries()].map(([driverId, [gx, gy]]) => {
          const color = teamColor(driverId)
          return (
            <g key={`ghost-${driverId}`} transform={`translate(${gx.toFixed(1)},${gy.toFixed(1)})`} opacity={0.35} pointerEvents="none">
              <circle r={7} fill="none" stroke={color} strokeWidth={1.5} />
            </g>
          )
        })}

        {/* Pit lane cars — in the pit pocket */}
        {pitDrivers.map((driverId, i) => {
          const color = teamColor(driverId)
          const cx = PIT_BOX_X + 7 + i * PIT_CAR_SPACING
          return (
            <g key={driverId} transform={`translate(${cx},${PIT_BOX_CAR_Y})`}>
              <circle r={7} fill={color} opacity={0.9} />
              <text
                x={0}
                y={-11}
                textAnchor="middle"
                fill="#ffffff"
                fontSize={8}
                fontFamily="'Barlow Condensed', sans-serif"
                fontWeight={700}
                letterSpacing="0.04em"
              >
                {driverId}
              </text>
            </g>
          )
        })}
      </svg>

      <span className="note">{positionsData ? 'LIVE TELEMETRY' : 'SCHEMATIC · INTERPOLATED'}</span>
    </div>
  )
})
