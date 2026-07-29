import { useMemo } from 'react'
import type { CSSProperties } from 'react'
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
  sessionStatus: string
  onSelectDriver: (id: string) => void
}

const statusLabel = (status: string) => ({
  started: 'GREEN',
  safety_car: 'SAFETY CAR',
  vsc: 'VIRTUAL SC',
  red_flag: 'RED FLAG',
  finished: 'FINISHED',
}[status] ?? status.replaceAll('_', ' ').toUpperCase())

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
  sessionStatus,
  onSelectDriver,
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
  const paceMin = pace[0]?.average ?? 0
  const paceMax = pace[pace.length - 1]?.average ?? paceMin
  const paceRange = Math.max(1, paceMax - paceMin)

  return (
    <section className="battle-intelligence" aria-label="Battle intelligence">
      <header className="bi-heading">
        <div>
          <small>OFFICIAL ORDER · MEASURED GAPS · RACE CONTEXT</small>
          <h1>BATTLE INTELLIGENCE</h1>
        </div>
        <span>NO INFERRED TRACK POSITION</span>
      </header>

      <div className="bi-grid">
        {rows.length === 0 ? (
          <div className="bi-formation">
            <small>SESSION READY</small>
            <strong>FORMATION LAP</strong>
            <p>Press PLAY. Official order, measured gaps and battle cards appear at lights out.</p>
          </div>
        ) : (
          <>
        <article className="bi-card bi-flow">
          <div className="bi-card-head">
            <b>LEAD FLOW · OFFICIAL ORDER</b>
            <span>{leadFlow[1]?.interval_s != null && leadFlow[1].interval_s <= 1 ? 'ATTACK RANGE' : 'CONFIRMED'}</span>
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
            <b>RACE STATE</b>
            <span>{statusLabel(sessionStatus)}</span>
          </div>
          <div className="bi-lap">
            {currentLap || '—'} <small>/ {totalLaps ?? '—'} LAPS</small>
          </div>
          <div className="bi-state-grid">
            <div><span>LEADER</span><strong>{rows[0]?.id ?? '—'}</strong></div>
            <div><span>TRACK</span><strong>{statusLabel(sessionStatus)}</strong></div>
            <div><span>BATTLES</span><strong>{battles.length}</strong></div>
            <div><span>FASTEST</span><strong>{fastest?.id ?? '—'}</strong></div>
            <div><span>RUNNING</span><strong>{rows.filter((row) => !row.retired).length}</strong></div>
            <div><span>ORDER</span><strong>OFFICIAL</strong></div>
          </div>
        </article>

        <article className="bi-card bi-battles">
          <div className="bi-card-head">
            <b>ACTIVE BATTLES</b>
            <span>{battles.length} GROUPS</span>
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
                  onClick={() => onSelectDriver(chaserId)}
                >
                  <span>P{leader?.position ?? '—'}</span>
                  <strong>{leaderId} / {chaserId}</strong>
                  <i><b style={{ width: `${strength}%` }} /></i>
                  <em>{gap.toFixed(2)}s</em>
                </button>
              )
            })}
            {battles.length === 0 && <div className="bi-empty">No confirmed close battle right now.</div>}
          </div>
        </article>

        <article className="bi-card bi-pace">
          <div className="bi-card-head">
            <b>LAST 5 LAPS · RELATIVE PACE</b>
            <span>LOWER IS BETTER</span>
          </div>
          <div className="bi-pace-chart">
            {pace.map(({ row, average }) => {
              const height = 45 + ((paceMax - average) / paceRange) * 55
              return (
                <button
                  type="button"
                  key={row.id}
                  onClick={() => onSelectDriver(row.id)}
                  style={{ '--pace-height': `${height}%`, '--team': teamColor(row.id) } as CSSProperties}
                  title={`${row.id} · ${formatLapTime(average)}`}
                >
                  <i />
                  <span>{row.id}</span>
                </button>
              )
            })}
            {pace.length === 0 && <div className="bi-empty">Pace appears after completed laps.</div>}
          </div>
        </article>
          </>
        )}
      </div>
    </section>
  )
}
