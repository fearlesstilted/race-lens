import React from 'react'
import type { DriverState } from '../../api/types'
import { teamColor } from './teamColors'

type Props = {
  selectedIds: string[]
  drivers: Record<string, DriverState>
}

function fmtLap(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return '—'
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const t = Math.floor((ms % 1000) / 100)
  return `${m}:${String(s).padStart(2, '0')}.${t}`
}

function fmtGap(s: number | null): string {
  if (s === null) return '—'
  return `+${s.toFixed(1)}s`
}

function recentLaps(driver: DriverState): number[] {
  const raw = (driver as Record<string, unknown>)['recent_laps_ms']
  if (Array.isArray(raw)) return (raw as number[]).filter((v) => v > 0).slice(-3)
  if (driver.last_lap_ms && driver.last_lap_ms > 0) return [driver.last_lap_ms]
  return []
}

function DriverCard({ driverId, driver }: { driverId: string; driver: DriverState }) {
  const color = teamColor(driverId)
  const laps = recentLaps(driver)
  const compound = driver.tyre_compound?.charAt(0).toUpperCase() ?? '?'

  return (
    <div className="focus-card">
      <div className="focus-head" style={{ borderLeftColor: color }}>
        <span className="focus-code" style={{ color }}>{driverId}</span>
        <span className="focus-pos">P{driver.position ?? '—'}</span>
        <span className="focus-gap">
          {driver.position === 1 ? 'LEADER' : fmtGap(driver.gap_s)}
        </span>
        <span className={`focus-tyre ty ${compound}`}>
          {compound}<span className="age">{driver.tyre_age_laps ?? '—'}</span>
        </span>
        <span className="focus-pits">{driver.pit_count ?? 0} PIT{(driver.pit_count ?? 0) !== 1 ? 'S' : ''}</span>
      </div>
      <div className="focus-laps">
        {laps.length === 0 && <span className="focus-lap-cell dim">—</span>}
        {laps.map((ms, i) => {
          const prev = laps[i - 1]
          const delta = prev !== undefined ? ms - prev : null
          return (
            <span key={i} className="focus-lap-cell">
              <span className="focus-lap-time">{fmtLap(ms)}</span>
              {delta !== null && (
                <span className={`focus-lap-delta ${delta < 0 ? 'up' : 'down'}`}>
                  {delta < 0 ? '▲' : '▼'}{Math.abs(delta / 1000).toFixed(2)}
                </span>
              )}
            </span>
          )
        })}
      </div>
      {driver.interval_s !== null && driver.position !== 1 && (
        <div className="focus-int">
          INT <b>+{driver.interval_s.toFixed(2)}s</b> to car ahead
        </div>
      )}
    </div>
  )
}

function DeltaRow({ a, b, driverA, driverB }: {
  a: string
  b: string
  driverA: DriverState
  driverB: DriverState
}) {
  const gapDiff = driverA.gap_s !== null && driverB.gap_s !== null
    ? Math.abs(driverA.gap_s - driverB.gap_s)
    : null
  const lastDiff = driverA.last_lap_ms !== null && driverB.last_lap_ms !== null
    ? driverA.last_lap_ms - driverB.last_lap_ms
    : null
  const tyreDiff = driverA.tyre_age_laps !== null && driverB.tyre_age_laps !== null
    ? driverA.tyre_age_laps - driverB.tyre_age_laps
    : null

  return (
    <div className="focus-delta-row">
      <span>Δ GAP <b>{gapDiff !== null ? `${gapDiff.toFixed(1)}s` : '—'}</b></span>
      <span>Δ LAST <b>{lastDiff !== null ? `${(Math.abs(lastDiff) / 1000).toFixed(2)}s (${lastDiff < 0 ? a : b} faster)` : '—'}</b></span>
      <span>Δ TYRE <b>{tyreDiff !== null ? `${Math.abs(tyreDiff)} lap${Math.abs(tyreDiff) !== 1 ? 's' : ''} (${tyreDiff > 0 ? a : b} older)` : '—'}</b></span>
    </div>
  )
}

export const FocusPanel = React.memo(function FocusPanel({ selectedIds, drivers }: Props) {
  if (selectedIds.length === 0) return null

  const [idA, idB] = selectedIds
  const driverA = drivers[idA]
  const driverB = idB ? drivers[idB] : null

  if (!driverA) return null

  const isH2H = driverB !== null && idB !== undefined

  return (
    <div className="focus-panel">
      {isH2H && <div className="focus-h2h-label">HEAD TO HEAD</div>}
      <div className={`focus-cards ${isH2H ? 'h2h' : ''}`}>
        <DriverCard driverId={idA} driver={driverA} />
        {isH2H && driverB && <DriverCard driverId={idB!} driver={driverB} />}
      </div>
      {isH2H && driverB && (
        <DeltaRow a={idA} b={idB!} driverA={driverA} driverB={driverB} />
      )}
    </div>
  )
})
