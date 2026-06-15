/**
 * ForecastStrip — shows PROJECTED FINISH (+10 LAPS) order with delta positions.
 * Only rendered when PROJECTION is on and a sessionId is available (replay only).
 */
import React, { useEffect, useRef, useState } from 'react'
import { getForecast } from '../../api/client'
import type { Forecast } from '../../api/types'

type Props = {
  sessionId: string
  atMs: number
}

const DEBOUNCE_MS = 300
const TOP_N = 8

function deltaMark(delta: number): { text: string; cls: string } {
  if (delta > 0) return { text: `▲${delta}`, cls: 'proj-up' }
  if (delta < 0) return { text: `▼${Math.abs(delta)}`, cls: 'proj-dn' }
  return { text: '=', cls: 'proj-eq' }
}

export const ForecastStrip = React.memo(function ForecastStrip({ sessionId, atMs }: Props) {
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      getForecast(sessionId, atMs, 10)
        .then(setForecast)
        .catch(() => undefined)
    }, DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [sessionId, atMs])

  if (!forecast) return null

  const top = forecast.projected_order.slice(0, TOP_N)

  return (
    <div className="forecast-strip">
      <div className="forecast-label">PROJECTED FINISH +{forecast.laps_ahead} LAPS</div>
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
