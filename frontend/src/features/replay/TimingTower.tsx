import React, { useMemo } from 'react'
import type { Battle, DriverState } from '../../api/types'
import { teamColor } from './teamColors'

type DriverRow = { id: string } & DriverState

type Props = {
  rows: DriverRow[]
  battles: Battle[]
}

function fmtLastLap(ms: number | null): string {
  if (ms === null || ms <= 0) return '—'
  const totalMs = ms
  const m = Math.floor(totalMs / 60000)
  const s = Math.floor((totalMs % 60000) / 1000)
  const t = Math.floor((totalMs % 1000) / 100)
  return `${m}:${String(s).padStart(2, '0')}.${t}`
}

export const TimingTower = React.memo(function TimingTower({ rows, battles }: Props) {
  const battleSet = useMemo(() => {
    const s = new Set<string>()
    for (const b of battles) {
      s.add(b.leader_id)
      s.add(b.chaser_id)
    }
    return s
  }, [battles])

  return (
    <div className="col col-timing">
      <div className="label">TIMING</div>
      {/* Column headers */}
      <div className="trow-hdr">
        <span>POS</span>
        <span />
        <span>DRV</span>
        <span>INT</span>
        <span>GAP</span>
        <span>LAST</span>
        <span>TYR</span>
        <span>PIT</span>
      </div>
      {rows.map((row) => {
        const isLead = row.position === 1
        const inBattle = battleSet.has(row.id)
        const color = teamColor(row.id)

        const intDisplay = isLead
          ? <span className="gap dim">—</span>
          : row.interval_s !== null
            ? <span className="gap">{`+${row.interval_s.toFixed(3)}`}</span>
            : <span className="gap dim">—</span>

        const gapDisplay = isLead
          ? <span className="gap dim">LEADER</span>
          : <span className={`gap${row.gap_s === null ? ' dim' : ''}`}>
              {row.gap_s !== null ? `+${row.gap_s.toFixed(1)}` : '—'}
            </span>

        const compound = row.tyre_compound?.charAt(0).toUpperCase() ?? '?'

        return (
          <div
            key={row.id}
            className={[
              'trow',
              isLead ? 'lead' : '',
              inBattle ? 'battle-tick' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span className="pos">{row.position ?? '—'}</span>
            <span className="tbar" style={{ background: color }} />
            <span className="code">
              {row.id}
              {row.in_pit && <span className="pit-tag">PIT</span>}
            </span>
            {intDisplay}
            {gapDisplay}
            <span className="last-lap">{fmtLastLap(row.last_lap_ms)}</span>
            <span className={`ty ${compound}`}>{compound}<span className="age">{row.tyre_age_laps ?? '—'}</span></span>
            <span className="pits-count">{row.pit_count ?? 0}</span>
          </div>
        )
      })}
      {rows.length === 0 && <div className="trow-empty">No data</div>}
    </div>
  )
})
