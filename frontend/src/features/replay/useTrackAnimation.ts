/**
 * Track-map animation hook. Owns the rAF loop, mutable refs, and imperative
 * SVG updates. Two modes:
 *  - Real telemetry: interpolate XY directly from positions data.
 *  - Schematic fallback: dead-reckoning + soft correction along the SVG path.
 */
import { useEffect, useRef } from 'react'
import type { DriverState } from '../../api/types'
import type { PositionsData } from '../../lib/liveGaps'
import { DEFAULT_LAP_MS } from '../../lib/liveGaps'
import { interpolateRealPos, median } from '../../lib/trackGeometry'
import { advanceFraction, computeTargetFractions, statusDrMultiplier } from '../../lib/deadReckoning'

type Args = {
  atMs: number
  playing: boolean
  playbackSpeed: number
  drivers: Record<string, DriverState>
  classification: string[]
  sessionStatus?: string
  positionsData: PositionsData | null
}

export type TrackAnimation = {
  /** Ref for the invisible measurement <path> (schematic mode). */
  pathRef: React.RefObject<SVGPathElement | null>
  /** Callback ref factory for each car's <g> element. */
  registerCar: (driverId: string) => (el: SVGGElement | null) => void
}

export function useTrackAnimation({
  atMs, playing, playbackSpeed, drivers, classification, sessionStatus, positionsData,
}: Args): TrackAnimation {
  const pathRef = useRef<SVGPathElement>(null)

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

  const playingRef = useRef(playing)
  useEffect(() => { playingRef.current = playing }, [playing])

  const playbackSpeedRef = useRef(playbackSpeed)
  useEffect(() => { playbackSpeedRef.current = playbackSpeed }, [playbackSpeed])

  const sessionStatusRef = useRef(sessionStatus ?? '')
  useEffect(() => { sessionStatusRef.current = sessionStatus ?? '' }, [sessionStatus])

  // Per-driver estimated lap ms (for dead reckoning)
  const driverLapMsRef = useRef<Map<string, number>>(new Map())

  // Peloton median fallback — updated on each drivers change
  const pelotonMedianRef = useRef<number>(DEFAULT_LAP_MS)

  const positionsDataRef = useRef<PositionsData | null>(null)
  useEffect(() => { positionsDataRef.current = positionsData }, [positionsData])

  const atMsRef = useRef(atMs)
  useEffect(() => { atMsRef.current = atMs }, [atMs])

  // Render current positions imperatively via SVG element refs.
  function renderPositions(overrideAtMs?: number) {
    const posData = positionsDataRef.current
    if (posData) {
      const queryMs = overrideAtMs ?? localAtMsRef.current
      for (const [driverId, groupEl] of carGroupRefs.current) {
        const xy = interpolateRealPos(posData, driverId, queryMs)
        if (xy === null) {
          groupEl.setAttribute('visibility', 'hidden')
        } else {
          groupEl.setAttribute('visibility', 'visible')
          groupEl.setAttribute('transform', `translate(${xy[0]},${xy[1]})`)
        }
      }
    } else {
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

  // Update target fractions whenever atMs / drivers / classification change
  useEffect(() => {
    const newTargets = computeTargetFractions(atMs, drivers, classification)
    targetFracRef.current = newTargets

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
        renderPositions(atMs)
      } else {
        for (const [id, frac] of newTargets) {
          currentFracRef.current.set(id, frac)
        }
        renderPositions()
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atMs, drivers, classification])

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

    localAtMsRef.current = atMsRef.current

    function tick(timestamp: number) {
      const dt = lastTimestampRef.current !== null ? timestamp - lastTimestampRef.current : 16
      lastTimestampRef.current = timestamp

      const speed = playbackSpeedRef.current

      if (positionsDataRef.current) {
        localAtMsRef.current += dt * speed
        renderPositions()
      } else {
        const drMultiplier = statusDrMultiplier(sessionStatusRef.current)
        const pelotonMs = pelotonMedianRef.current

        for (const [id, target] of targetFracRef.current) {
          const current = currentFracRef.current.get(id) ?? target
          const lapMs = driverLapMsRef.current.get(id) ?? pelotonMs
          const next = advanceFraction(current, target, dt, speed, lapMs, drMultiplier)
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
  useEffect(() => {
    const ids = new Set(classification)
    for (const id of carGroupRefs.current.keys()) {
      if (!ids.has(id)) {
        carGroupRefs.current.delete(id)
        currentFracRef.current.delete(id)
      }
    }
  }, [classification])

  const registerCar = (driverId: string) => (el: SVGGElement | null) => {
    if (el) carGroupRefs.current.set(driverId, el)
    else carGroupRefs.current.delete(driverId)
  }

  return { pathRef, registerCar }
}
