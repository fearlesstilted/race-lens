import { useMemo } from 'react'
import type { Battle, DriverState } from '../../api/types'
import { battleGap, battlePair } from '../../lib/battles'
import { formatLapTime } from '../../lib/format'
import { teamColor } from './teamColors'

type DriverRow = { id: string } & DriverState

type Props = {
  rows: DriverRow[]
  battles: Battle[]
  currentLap: number
  totalLaps: number | null
  onSelectDriver: (id: string) => void
  onSelectBattle: (ids: string[]) => void
}

const recentPace = (driver: DriverRow): number | null => {
  const laps = driver.recent_laps_ms.filter((lap) => lap > 0).slice(-5)
  if (laps.length === 0) return driver.last_lap_ms && driver.last_lap_ms > 0
    ? driver.last_lap_ms
    : null
  return laps.reduce((sum, lap) => sum + lap, 0) / laps.length
}

export function BattleIntelligence({
  rows,
  battles,
  currentLap,
  totalLaps,
  onSelectDriver,
  onSelectBattle,
}: Props) {
  const leadFlow = rows.slice(0, 3)
  const byId = useMemo(() => new Map(rows.map((row) => [row.id, row])), [rows])
  const fastest = useMemo(() => rows.reduce<DriverRow | null>((best, row) => {
    if (!row.best_lap_ms || row.best_lap_ms <= 0) return best
    return !best || !best.best_lap_ms || row.best_lap_ms < best.best_lap_ms ? row : best
  }, null), [rows])
  const pace = useMemo(() => rows
    .filter((row) => !row.retired)
    .map((row) => ({ row, average: recentPace(row) }))
    .filter((item): item is { row: DriverRow; average: number } => item.average !== null)
    .sort((a, b) => a.average - b.average)
    .slice(0, 7), [rows])
  const fastestPace = pace[0]?.average

  return (
    <section className="battle-intelligence" aria-label="Battle intelligence">
      <div className="bi-grid">
        {rows.length === 0 ? (
          <div className="bi-formation">
            <small>SESSION READY</small>
            <strong>FORMATION LAP</strong>
          </div>
        ) : (
          <>
        <article className="bi-card bi-flow">
          <div className="bi-card-head">
            <b>TOP 3</b>
          </div>
          <div className="bi-flow-list">
            {leadFlow.map((driver, index) => (
              <div key={driver.id}>
                {index > 0 && (
                  <div className={`bi-gap-link${(driver.interval_s ?? 99) <= 1 ? ' hot' : ''}`}>
                    {driver.interval_s != null ? `${driver.interval_s.toFixed(2)}s` : '—'}
                  </div>
                )}
                <button
                  type="button"
                  className="bi-driver"
                  onClick={() => onSelectDriver(driver.id)}
                >
                  <span className="bi-rank">P{driver.position ?? index + 1}</span>
                  <i style={{ background: teamColor(driver.id) }} />
                  <strong>{driver.id}</strong>
                  <span className="bi-driver-meta">
                    <b>{driver.retired ? 'OUT' : `${driver.tyre_compound ?? 'Unknown'} · ${driver.tyre_age_laps ?? '—'} laps`}</b>
                    <small>{formatLapTime(driver.last_lap_ms)}</small>
                  </span>
                  <span className="bi-driver-gap">
                    {index === 0 ? 'LEADER' : driver.gap_s != null ? `+${driver.gap_s.toFixed(2)}` : '—'}
                  </span>
                </button>
              </div>
            ))}
            {leadFlow.length === 0 && <div className="bi-empty">Waiting for classification…</div>}
          </div>
        </article>

        <article className="bi-card bi-state">
          <div className="bi-card-head">
            <b>RACE</b>
          </div>
          <div className="bi-lap">
            {currentLap || '—'} <small>/ {totalLaps ?? '—'} LAPS</small>
          </div>
          <div className="bi-state-grid">
            <div><span>LEADER</span><strong>{rows[0]?.id ?? '—'}</strong></div>
            <div><span>FASTEST</span><strong>{fastest?.id ?? '—'}</strong></div>
            <div><span>RUNNING</span><strong>{rows.filter((row) => !row.retired).length}</strong></div>
          </div>
        </article>

        <article className="bi-card bi-battles">
          <div className="bi-card-head">
            <b>ACTIVE BATTLES · {battles.length}</b>
          </div>
          <div className="bi-battle-list">
            {battles.slice(0, 5).map((battle) => {
              const pair = battlePair(battle)
              const gap = battleGap(battle)
              if (!pair || gap === null) return null
              const [leaderId, chaserId] = pair
              const leader = byId.get(leaderId)
              const strength = Math.max(8, 100 - Math.min(100, gap * 45))
              return (
                <button
                  type="button"
                  className="bi-battle-row"
                  key={`${leaderId}-${chaserId}`}
                  onClick={() => onSelectBattle([leaderId, chaserId])}
                >
                  <span>P{leader?.position ?? '—'}</span>
                  <strong>{leaderId} / {chaserId}</strong>
                  <i><b style={{ width: `${strength}%` }} /></i>
                  <em>{gap.toFixed(2)}s</em>
                </button>
              )
            })}
            {battles.length === 0 && <div className="bi-empty">No active battles right now.</div>}
          </div>
        </article>

        <article className="bi-card bi-pace">
          <div className="bi-card-head">
            <b>5-LAP PACE</b>
          </div>
          <div className="bi-pace-list">
            {pace.map(({ row, average }) => {
              const delta = average - (fastestPace ?? average)
              return (
                <button
                  type="button"
                  className="bi-pace-row"
                  key={row.id}
                  onClick={() => onSelectDriver(row.id)}
                  title={`${row.id} · ${formatLapTime(average)}`}
                >
                  <i style={{ background: teamColor(row.id) }} />
                  <strong>{row.id}</strong>
                  <span>{formatLapTime(average)}</span>
                  <em>{delta === 0 ? 'FASTEST' : `+${(delta / 1000).toFixed(3)}s`}</em>
                </button>
              )
            })}
            {pace.length === 0 && <div className="bi-empty">Complete a lap to compare pace.</div>}
          </div>
        </article>
          </>
        )}
      </div>
    </section>
  )
}
