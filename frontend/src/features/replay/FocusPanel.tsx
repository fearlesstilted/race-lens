import React, { useMemo } from 'react'
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

/** Detect if a lap time is an in/out-lap: 10+ seconds slower than median of recent laps */
function isPitLap(driver: DriverState): boolean {
  if (!driver.last_lap_ms || driver.last_lap_ms <= 0) return false
  const raw = (driver as Record<string, unknown>)['recent_laps_ms']
  let medMs: number | null = null
  if (Array.isArray(raw) && (raw as number[]).length > 0) {
    const valid = (raw as number[]).filter((v) => v > 0)
    if (valid.length > 0) {
      const sorted = [...valid].sort((a, b) => a - b)
      const mid = Math.floor(sorted.length / 2)
      medMs = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
    }
  }
  if (medMs === null) return false
  return (driver.last_lap_ms - medMs) >= 10000
}

/** Single-driver card (non-H2H mode) */
function DriverCard({ driverId, driver }: { driverId: string; driver: DriverState }) {
  const color = teamColor(driverId)
  const laps = recentLaps(driver)
  const compound = driver.tyre_compound?.charAt(0).toUpperCase() ?? '?'
  const inPit = driver.in_pit
  const pitLap = !inPit && isPitLap(driver)

  return (
    <div className="focus-card">
      <div className="focus-head" style={{ borderLeftColor: color }}>
        <span className="focus-code" style={{ color }}>{driverId}</span>
        {inPit && <span className="focus-inpit-badge">IN PIT</span>}
        <span className="focus-pos">P{driver.position ?? '—'}</span>
        <span className="focus-gap">
          {driver.position === 1 ? 'LEADER' : fmtGap(driver.gap_s)}
        </span>
        <span className={`focus-tyre ty ${compound}`}>
          {compound}<span className="age">{driver.tyre_age_laps ?? '—'}</span>
        </span>
        <span className="focus-pits" style={{ fontSize: 13 }}>{driver.pit_count ?? 0}×PIT</span>
      </div>
      <div className="focus-laps">
        {laps.length === 0 && <span className="focus-lap-cell dim">—</span>}
        {laps.map((ms, i) => {
          const prev = laps[i - 1]
          const delta = prev !== undefined ? ms - prev : null
          const isLast = i === laps.length - 1
          return (
            <span key={i} className="focus-lap-cell">
              <span className="focus-lap-time">{fmtLap(ms)}</span>
              {isLast && pitLap && (
                <span className="focus-pitlap-ann">PIT LAP</span>
              )}
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

/** H2H half-panel for one driver */
function H2HDriver({ driverId, driver }: { driverId: string; driver: DriverState }) {
  const color = teamColor(driverId)
  const laps = recentLaps(driver)
  const compound = driver.tyre_compound?.charAt(0).toUpperCase() ?? '?'

  return (
    <div className="h2h-half">
      <div className="h2h-code" style={{ color }}>{driverId}</div>
      <div className="h2h-meta">
        <span className="h2h-pos">P{driver.position ?? '—'}</span>
        <span className="h2h-gap">{driver.position === 1 ? 'LEADER' : fmtGap(driver.gap_s)}</span>
      </div>
      <div className="h2h-laps">
        {laps.length === 0 && <span className="h2h-lap-cell"><span className="h2h-lap-time">—</span></span>}
        {laps.map((ms, i) => {
          const prev = laps[i - 1]
          const delta = prev !== undefined ? ms - prev : null
          return (
            <span key={i} className="h2h-lap-cell">
              <span className="h2h-lap-time">{fmtLap(ms)}</span>
              {delta !== null && (
                <span className={`h2h-lap-delta ${delta < 0 ? 'up' : 'down'}`}>
                  {delta < 0 ? '▲' : '▼'}{Math.abs(delta / 1000).toFixed(2)}
                </span>
              )}
            </span>
          )
        })}
      </div>
      <div className="h2h-tyre-row">
        <span className={`ty ${compound}`}>{compound}<span className="age">{driver.tyre_age_laps ?? '—'}</span></span>
        <span className="h2h-pits">{driver.pit_count ?? 0}×PIT</span>
      </div>
    </div>
  )
}

function H2HDeltas({
  idA, idB, driverA, driverB,
}: {
  idA: string; idB: string; driverA: DriverState; driverB: DriverState
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
    <div className="h2h-deltas">
      <div className="h2h-delta-cell">
        <span className="h2h-delta-label">Δ GAP</span>
        <span className="h2h-delta-val">{gapDiff !== null ? `${gapDiff.toFixed(1)}s` : '—'}</span>
      </div>
      <div className="h2h-delta-cell">
        <span className="h2h-delta-label">Δ LAST</span>
        <span className="h2h-delta-val">
          {lastDiff !== null
            ? `${(Math.abs(lastDiff) / 1000).toFixed(2)}s`
            : '—'}
        </span>
        {lastDiff !== null && (() => {
          const fasterId = lastDiff < 0 ? idA : idB
          return (
            <span
              className="h2h-delta-who h2h-delta-faster"
              style={{ color: teamColor(fasterId) }}
            >{fasterId} faster</span>
          )
        })()}
      </div>
      <div className="h2h-delta-cell">
        <span className="h2h-delta-label">Δ TYRE</span>
        <span className="h2h-delta-val">
          {tyreDiff !== null ? `${Math.abs(tyreDiff)}L` : '—'}
        </span>
        {tyreDiff !== null && tyreDiff !== 0 && (
          <span className="h2h-delta-who">{tyreDiff > 0 ? idA : idB} older</span>
        )}
      </div>
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

  if (isH2H && driverB) {
    return (
      <div className="focus-panel focus-panel-h2h">
        <div className="focus-h2h-label">HEAD TO HEAD</div>
        <div className="h2h-body">
          <H2HDriver driverId={idA} driver={driverA} />
          <div className="h2h-divider" />
          <H2HDriver driverId={idB!} driver={driverB} />
        </div>
        <H2HDeltas idA={idA} idB={idB!} driverA={driverA} driverB={driverB} />
      </div>
    )
  }

  return (
    <div className="focus-panel">
      <div className="focus-cards">
        <DriverCard driverId={idA} driver={driverA} />
      </div>
    </div>
  )
})
