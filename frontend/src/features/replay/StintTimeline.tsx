/**
 * StintTimeline — per-driver tyre strategy bars (compound-coloured, width = laps).
 * The whole race strategy at a glance. Replay only; fetched once per session.
 */
import { getStints } from '../../api/client'
import type { StintsResponse } from '../../api/types'
import { clipStints } from '../../lib/stints'
import { compoundColor } from './teamColors'
import { useAsync } from './useAsync'

type Props = {
  sessionId: string
  currentLap: number
  /** Current classification order (driver ids) to sort rows by; falls back to map order. */
  order?: string[]
}

export function StintTimeline({ sessionId, currentLap, order }: Props) {
  const { data, loading, error } = useAsync<StintsResponse>(() => getStints(sessionId), [sessionId])

  if (loading) return <div className="stints stints-state">LOADING TYRE STRATEGY…</div>
  if (!data || error || data.total_laps <= 0) return <div className="stints stints-state">TYRE STRATEGY UNAVAILABLE</div>
  const total = data.total_laps
  const ruler = [1, Math.ceil(total / 4), Math.ceil(total / 2), Math.ceil(total * 3 / 4), total]

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
      <div className="stint-legend" aria-label="Tyre compound legend">
        {['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'].map((compound) => (
          <span key={compound}><i style={{ background: compoundColor(compound) }} />{compound}</span>
        ))}
      </div>
      <div className="stint-ruler" aria-label="Race lap ruler">
        <span />
        <span className="stint-ruler-laps">
          {ruler.map((lap, index) => <span key={`${lap}-${index}`}>L{lap}</span>)}
        </span>
      </div>
      <div className="stints-rows">
        {sorted.map((id) => (
          <div className="stint-row" key={id}>
            <span className="stint-drv">{id}</span>
            <span className="stint-bar">
              {clipStints(data.stints[id], currentLap).map((s, i) => (
                <span
                  key={i}
                  className="stint-seg"
                  style={{ left: `${((s.start_lap - 1) / total) * 100}%`, width: `${(s.laps / total) * 100}%`, background: compoundColor(s.compound) }}
                  title={`${s.compound} · L${s.start_lap}-${s.end_lap} (${s.laps})`}
                >
                  <span className="stint-seg-lbl">{s.compound} L{s.start_lap}–{s.end_lap}</span>
                </span>
              ))}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
