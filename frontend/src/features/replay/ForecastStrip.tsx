/**
 * ForecastStrip — shows an experimental short-horizon pace outlook.
 * Only rendered when PROJECTION is on and a sessionId (replay) or `live` (live
 * mode, via the /api/live/forecast mirror) is available.
 */
import React, { useEffect, useRef, useState } from 'react'
import { getForecast, getLiveForecast } from '../../api/client'
import type { Forecast } from '../../api/types'

type Props = {
  sessionId?: string | null
  atMs: number
  /** Live mode: fetch from /api/live/forecast instead of the session-scoped endpoint. */
  live?: boolean
}

// Throttle rather than debounce: during play atMs ticks continuously and a
// debounce would never fire until pause (the old bug). Throttle fires on the
// leading edge then at most every THROTTLE_MS, with a trailing fetch on stop.
const THROTTLE_MS = 1500
const TOP_N = 8

function deltaMark(delta: number): { text: string; cls: string } {
  if (delta > 0) return { text: `▲${delta}`, cls: 'proj-up' }
  if (delta < 0) return { text: `▼${Math.abs(delta)}`, cls: 'proj-dn' }
  return { text: '=', cls: 'proj-eq' }
}

export const ForecastStrip = React.memo(function ForecastStrip({ sessionId, atMs, live }: Props) {
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const lastFetch = useRef(0)

  useEffect(() => {
    setForecast(null)
    lastFetch.current = 0
  }, [sessionId, live])

  useEffect(() => {
    let cancelled = false
    const run = () => {
      lastFetch.current = Date.now()
      const req = live ? getLiveForecast(10) : sessionId ? getForecast(sessionId, atMs, 10) : null
      req?.then((value) => { if (!cancelled) setForecast(value) })
        .catch(() => { if (!cancelled) setForecast(null) })
    }
    const elapsed = Date.now() - lastFetch.current
    if (elapsed >= THROTTLE_MS) {
      run()
      return () => { cancelled = true }
    }
    const t = setTimeout(run, THROTTLE_MS - elapsed)
    return () => { cancelled = true; clearTimeout(t) }
  }, [sessionId, atMs, live])

  if (!forecast) return null

  const top = forecast.projected_order.slice(0, TOP_N)

  return (
    <div className="forecast-strip">
      <div className="forecast-label">
        PACE OUTLOOK · +{forecast.effective_laps ?? forecast.laps_ahead} LAPS · UNCALIBRATED
      </div>
      <div className="forecast-rows">
        {top.map((driverId, i) => {
          const proj = forecast.projected[driverId]
          const delta = proj ? deltaMark(proj.delta_pos) : { text: '=', cls: 'proj-eq' }
          return (
            <span key={driverId} className="forecast-row">
              <span className="forecast-pos">P{i + 1}</span>
              <span className="forecast-id">{driverId}</span>
              <span className={`forecast-delta ${delta.cls}`}>{delta.text}</span>
            </span>
          )
        })}
      </div>
    </div>
  )
})
