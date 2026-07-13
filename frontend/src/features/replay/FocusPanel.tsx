import React, { useCallback, useState } from 'react'
import { getLiveSimulatePit, getSimulatePit, getWhatIf } from '../../api/client'
import type { DriverState, PitSim, PitSimEvidence, WhatIf, WhatIfDiff } from '../../api/types'
import { teamColor } from './teamColors'

type Props = {
  selectedIds: string[]
  drivers: Record<string, DriverState>
  /** Session ID for pit-sim/what-if (replay only; null in live). */
  sessionId: string | null
  /** Live mode: PIT NOW uses /api/live/simulate-pit instead (WHAT IF has no live mirror). */
  live?: boolean
  atMs: number
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
  const raw = driver.recent_laps_ms
  if (Array.isArray(raw)) return raw.filter((v) => v > 0).slice(-3)
  if (driver.last_lap_ms && driver.last_lap_ms > 0) return [driver.last_lap_ms]
  return []
}

/** Detect if a lap time is an in/out-lap: 10+ seconds slower than median of recent laps */
function isPitLap(driver: DriverState): boolean {
  if (!driver.last_lap_ms || driver.last_lap_ms <= 0) return false
  const raw = driver.recent_laps_ms
  let medMs: number | null = null
  if (Array.isArray(raw) && raw.length > 0) {
    const valid = raw.filter((v) => v > 0)
    if (valid.length > 0) {
      const sorted = [...valid].sort((a, b) => a - b)
      const mid = Math.floor(sorted.length / 2)
      medMs = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
    }
  }
  if (medMs === null) return false
  return (driver.last_lap_ms - medMs) >= 10000
}

/** Pit sim verdict card */
function PitSimCard({ ev }: { ev: PitSimEvidence }) {
  const verdictColor = ev.verdict === 'UNDERCUT_LIKELY' ? '#00c853' : ev.verdict === 'UNLIKELY' ? '#f2a900' : '#a0a0ac'
  const verdictText = ev.verdict === 'UNDERCUT_LIKELY' ? 'UNDERCUT LIKELY' : ev.verdict === 'UNLIKELY' ? 'UNLIKELY' : 'NO RIVAL'
  return (
    <div className="pit-sim-card">
      <div className="pit-sim-verdict" style={{ color: verdictColor }}>{verdictText}</div>
      <div className="pit-sim-rows">
        <span>REJOINS P{ev.rejoin_pos}</span>
        {ev.key_rival && ev.margin_s !== null && (
          <span>VS {ev.key_rival}: MARGIN {ev.margin_s.toFixed(1)}s</span>
        )}
        <span>PIT LOSS {ev.pit_loss_s.toFixed(1)}s</span>
      </div>
    </div>
  )
}

/** What-If result card */
function WhatIfCard({ result, lang }: { result: WhatIf; lang?: string }) {
  const summary = lang === 'ru' ? result.summary_text_ru : result.summary_text_en
  const topMovers = result.diff.filter((d) => d.delta !== 0).slice(0, 5)

  return (
    <div className="what-if-card">
      <div className="what-if-summary">{summary}</div>
      {topMovers.length > 0 && (
        <div className="what-if-diff">
          {topMovers.map((d: WhatIfDiff) => (
            <div key={d.driver} className="what-if-diff-row">
              <span className="what-if-driver" style={{ color: teamColor(d.driver) }}>{d.driver}</span>
              <span className="what-if-pos-from">P{d.baseline_pos}</span>
              <span className="what-if-arrow">→</span>
              <span className="what-if-pos-to">P{d.scenario_pos}</span>
              <span className={`what-if-delta ${d.delta > 0 ? 'up' : 'down'}`}>
                {d.delta > 0 ? `▲${d.delta}` : `▼${Math.abs(d.delta)}`}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="what-if-note">strategy sensitivity · uncalibrated</div>
    </div>
  )
}

/** Single-driver card (non-H2H mode) */
function DriverCard({ driverId, driver, sessionId, live, atMs }: { driverId: string; driver: DriverState; sessionId: string | null; live?: boolean; atMs: number }) {
  const color = teamColor(driverId)
  const laps = recentLaps(driver)
  const compound = driver.tyre_compound?.charAt(0).toUpperCase() ?? '?'
  const inPit = driver.in_pit
  const pitLap = !inPit && isPitLap(driver)
  const [pitSim, setPitSim] = useState<PitSim | null>(null)
  const [pitBusy, setPitBusy] = useState(false)
  const [whatIf, setWhatIf] = useState<WhatIf | null>(null)
  const [whatIfBusy, setWhatIfBusy] = useState(false)
  const [whatIfScenario, setWhatIfScenario] = useState<string | null>(null)

  const handlePitNow = useCallback(() => {
    if (!sessionId && !live) return
    setPitBusy(true)
    const req = sessionId ? getSimulatePit(sessionId, atMs, driverId) : getLiveSimulatePit(driverId)
    req
      .then((res) => { setPitSim(res) })
      .catch(() => undefined)
      .finally(() => setPitBusy(false))
  }, [sessionId, live, atMs, driverId])

  const handleWhatIf = useCallback((scenario: string) => {
    if (!sessionId) return
    setWhatIfBusy(true)
    setWhatIfScenario(scenario)
    getWhatIf(sessionId, atMs, scenario, driverId)
      .then((res) => { setWhatIf(res) })
      .catch(() => undefined)
      .finally(() => setWhatIfBusy(false))
  }, [sessionId, atMs, driverId])

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
        <span className="focus-pits" style={{ fontSize: 14 }}>{driver.pit_count ?? 0}×PIT</span>
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
      {(sessionId || live) && (
        <div className="focus-pit-row">
          <button className="b pit-now-btn" type="button" onClick={handlePitNow} disabled={pitBusy}>
            {pitBusy ? '…' : 'PIT NOW'}
          </button>
          {pitSim && !pitSim.error && pitSim.evidence && <PitSimCard ev={pitSim.evidence} />}
          {pitSim?.error && <span className="live-err">{pitSim.error}</span>}
        </div>
      )}
      {sessionId && (
        // WHAT IF has no live mirror (server-side) — replay only.
        <div className="focus-whatif-section">
          <div className="focus-whatif-label">WHAT IF</div>
          <div className="focus-whatif-btns">
            <button
              className={`b whatif-btn${whatIfScenario === 'pit_now' ? ' active' : ''}`}
              type="button"
              onClick={() => handleWhatIf('pit_now')}
              disabled={whatIfBusy}
              title="Full race projection if driver pits right now"
            >
              {whatIfBusy && whatIfScenario === 'pit_now' ? '…' : 'PIT FINISH'}
            </button>
            <button
              className={`b whatif-btn${whatIfScenario === 'stay_out' ? ' active' : ''}`}
              type="button"
              onClick={() => handleWhatIf('stay_out')}
              disabled={whatIfBusy}
              title="Full race projection if driver stays out on current tyres"
            >
              {whatIfBusy && whatIfScenario === 'stay_out' ? '…' : 'STAY OUT'}
            </button>
          </div>
          {whatIf && !whatIfBusy && <WhatIfCard result={whatIf} />}
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

export const FocusPanel = React.memo(function FocusPanel({ selectedIds, drivers, sessionId, live, atMs }: Props) {
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
        <DriverCard key={idA} driverId={idA} driver={driverA} sessionId={sessionId} live={live} atMs={atMs} />
      </div>
    </div>
  )
})
