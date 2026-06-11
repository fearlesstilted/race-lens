import React, { useMemo } from 'react'
import type { Battle, DriverState } from '../../api/types'
import { teamColor } from './teamColors'

type DriverRow = { id: string } & DriverState

type Props = {
  rows: DriverRow[]
  battles: Battle[]
}

export function TimingTower({ rows, battles }: Props) {
  const battleSet = useMemo(() => {
    const s = new Set<string>()
    for (const b of battles) {
      s.add(b.leader_id)
      s.add(b.chaser_id)
    }
    return s
  }, [battles])

  const maxGap = useMemo(() => {
    let max = 0
    for (const r of rows) {
      if (r.gap_s !== null && r.gap_s > max) max = r.gap_s
    }
    return max || 1
  }, [rows])

  return (
    <div className="col col-timing">
      <div className="label">TIMING</div>
      {rows.map((row) => {
        const isLead = row.position === 1
        const inBattle = battleSet.has(row.id)
        const color = teamColor(row.id)
        const gapPct = row.gap_s !== null ? Math.min((row.gap_s / maxGap) * 100, 100) : 0

        let gapDisplay: React.ReactNode
        if (row.in_pit) {
          gapDisplay = <span className="gap amber">IN PIT</span>
        } else if (isLead) {
          gapDisplay = <span className="gap dim">LEADER</span>
        } else {
          gapDisplay = (
            <span className="gap">
              {row.gap_s !== null ? `+${row.gap_s.toFixed(1)}` : '—'}
            </span>
          )
        }

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
            <span className="code">{row.id}</span>
            <span className="gapline">
              <i style={{ width: `${gapPct}%` }} />
            </span>
            <span className={`ty ${compound}`}>{compound}</span>
            <span className="age">{row.tyre_age_laps ?? '—'}</span>
            {gapDisplay}
          </div>
        )
      })}
      {rows.length === 0 && <div className="trow-empty">No data</div>}
    </div>
  )
}
