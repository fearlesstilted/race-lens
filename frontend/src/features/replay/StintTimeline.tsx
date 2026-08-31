/**
 * StintTimeline — per-driver tyre strategy bars (compound-coloured, width = laps).
 * The whole race strategy at a glance. Live data arrives with each snapshot.
 */
import { getLiveStints, getStints } from '../../api/client'
import type { StintsResponse } from '../../api/types'
import { clipStints, showStintLabel } from '../../lib/stints'
import { compoundColor } from './teamColors'
import { useAsync } from './useAsync'

type Props = {
  sessionId: string | null
  live?: boolean
  liveData?: StintsResponse | null
  currentLap: number
  /** Current classification order (driver ids) to sort rows by; falls back to map order. */
  order?: string[]
  onSelectDriver?: (id: string) => void
}

export function StintTimeline({ sessionId, live = false, liveData = null, currentLap, order, onSelectDriver }: Props) {
  const fetched = useAsync<StintsResponse>(
    () => live ? getLiveStints() : getStints(sessionId!),
    [live, sessionId],
    !liveData,
  )
  const data = liveData ?? fetched.data
  const { loading, error } = fetched

  if (loading) return <div className="stints stints-state">LOADING TYRE STRATEGY…</div>
  if (!data || error || data.total_laps <= 0) return <div className="stints stints-state">TYRE STRATEGY UNAVAILABLE</div>
  const total = data.total_laps
  const currentPct = Math.min(100, Math.max(0, (currentLap / total) * 100))
  const ruler = [1, Math.ceil(total / 4), Math.ceil(total / 2), Math.ceil(total * 3 / 4), total]

  const ids = Object.keys(data.stints).filter((id) => data.stints[id].length > 0)
  if (ids.length === 0) return <div className="stints stints-state">TYRE STRATEGY UNAVAILABLE</div>
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
        <span className="stint-axis">
          <span className="stint-ruler-laps">
            {ruler.map((lap, index) => <span key={`${lap}-${index}`}>L{lap}</span>)}
          </span>
          {currentPct < 100 && (
            <span className="stint-future stint-future-axis" style={{ left: `${currentPct}%` }} aria-hidden="true" />
          )}
          <span className="stint-now stint-now-axis" style={{ left: `${currentPct}%` }}>
            <i>NOW · L{currentLap}</i>
          </span>
        </span>
      </div>
      <div className="stints-rows">
        {sorted.map((id) => (
          <div
            className={`stint-row${onSelectDriver ? ' stint-row-action' : ''}`}
            key={id}
            role={onSelectDriver ? 'button' : undefined}
            tabIndex={onSelectDriver ? 0 : undefined}
            onClick={onSelectDriver ? () => onSelectDriver(id) : undefined}
            onKeyDown={onSelectDriver ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelectDriver(id)
              }
            } : undefined}
          >
            <span className="stint-drv">{id}</span>
            <span className="stint-bar" aria-label={`${id} strategy through lap ${currentLap} of ${total}`}>
              {clipStints(data.stints[id], currentLap).map((s, i) => (
                <span
                  key={i}
                  className="stint-seg"
                  style={{ left: `${((s.start_lap - 1) / total) * 100}%`, width: `${(s.laps / total) * 100}%`, background: compoundColor(s.compound) }}
                  title={`${s.compound} · L${s.start_lap}-${s.end_lap} (${s.laps})`}
                >
                  {showStintLabel(s.laps, total) && (
                    <span className="stint-seg-lbl">{s.compound} L{s.start_lap}–{s.end_lap}</span>
                  )}
                </span>
              ))}
              {currentPct < 100 && <span className="stint-future" style={{ left: `${currentPct}%` }} />}
              <span className="stint-now" style={{ left: `${currentPct}%` }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
