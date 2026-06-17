/**
 * StintTimeline — per-driver tyre strategy bars (compound-coloured, width = laps).
 * The whole race strategy at a glance. Replay only; fetched once per session.
 */
import { useEffect, useState } from 'react'
import { getStints } from '../../api/client'
import type { StintsResponse } from '../../api/types'

type Props = {
  sessionId: string
  /** Current classification order (driver ids) to sort rows by; falls back to map order. */
  order?: string[]
}

const COMPOUND_COLOR: Record<string, string> = {
  SOFT: '#e8002d',
  MEDIUM: '#f2c500',
  HARD: '#e8e8ec',
  INTERMEDIATE: '#3cba54',
  WET: '#2d6fe8',
  UNKNOWN: '#5a5a63',
}

function compoundColor(c: string): string {
  return COMPOUND_COLOR[(c || '').toUpperCase()] ?? COMPOUND_COLOR.UNKNOWN
}

export function StintTimeline({ sessionId, order }: Props) {
  const [data, setData] = useState<StintsResponse | null>(null)

  useEffect(() => {
    let cancelled = false
    getStints(sessionId)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [sessionId])

  if (!data || data.total_laps <= 0) return null
  const total = data.total_laps

  const ids = Object.keys(data.stints)
  const sorted = order
    ? [...ids].sort((a, b) => {
        const ia = order.indexOf(a)
        const ib = order.indexOf(b)
        return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
      })
    : ids

  return (
    <div className="stints">
      <div className="stints-head">
        <span>TYRE STRATEGY</span>
        <span className="stints-laps">{total} LAPS</span>
      </div>
      <div className="stints-rows">
        {sorted.map((id) => (
          <div className="stint-row" key={id}>
            <span className="stint-drv">{id}</span>
            <span className="stint-bar">
              {data.stints[id].map((s, i) => (
                <span
                  key={i}
                  className="stint-seg"
                  style={{ width: `${(s.laps / total) * 100}%`, background: compoundColor(s.compound) }}
                  title={`${s.compound} · L${s.start_lap}-${s.end_lap} (${s.laps})`}
                >
                  {s.laps >= 4 && (
                    <span className="stint-seg-lbl">{s.compound.charAt(0)}{s.laps}</span>
                  )}
                </span>
              ))}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
