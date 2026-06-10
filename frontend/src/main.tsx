import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { listSessions } from './api/client'
import type { Insight, SessionSummary } from './api/types'
import { useReplay } from './features/replay/useReplay'
import { formatDeltaSeconds, formatLapTime, formatRaceTime, sessionLabel } from './lib/format'
import './style.css'

const SPEEDS = [1, 5, 10] as const

function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const replay = useReplay(sessionId)

  useEffect(() => {
    let cancelled = false
    listSessions()
      .then((items) => {
        if (cancelled) return
        setSessions(items)
        setSessionId((current) => current ?? items[0]?.session_id ?? null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setSessionError(err instanceof Error ? err.message : 'Could not load sessions')
      })

    return () => {
      cancelled = true
    }
  }, [])

  const state = replay.state
  const timeline = replay.timeline
  const maxMs = timeline?.end_ms ?? 0
  const rows = useMemo(
    () =>
      state?.classification.map((driverId) => ({
        id: driverId,
        ...state.drivers[driverId],
      })) ?? [],
    [state],
  )

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Race Lens</p>
          <h1>Replay companion</h1>
        </div>
        <div className={`quality quality-${state?.data_quality.status ?? 'unknown'}`}>
          <span>{state?.data_quality.status ?? 'offline'}</span>
          <strong>{state?.data_quality.events_applied ?? 0}</strong>
          <small>events applied</small>
        </div>
      </header>

      <section className="controls" aria-label="Replay controls">
        <label>
          Session
          <select
            value={sessionId ?? ''}
            onChange={(event) => {
              replay.pause()
              setSessionId(event.target.value || null)
            }}
          >
            {sessions.map((item) => (
              <option value={item.session_id} key={item.session_id}>
                {sessionLabel(item.session_id)}
              </option>
            ))}
          </select>
        </label>

        <label className="time-input">
          At time
          <input
            type="number"
            value={replay.atMs}
            min={timeline?.start_ms ?? 0}
            max={maxMs}
            step={10_000}
            onChange={(event) => replay.scrub(Number(event.target.value))}
          />
        </label>

        <div className="playback" aria-label="Playback controls">
          <button type="button" onClick={replay.play} disabled={!sessionId || replay.playing}>
            Play
          </button>
          <button type="button" onClick={replay.pause} disabled={!replay.playing}>
            Pause
          </button>
          <div className="speed-group" aria-label="Replay speed">
            {SPEEDS.map((speed) => (
              <button
                key={speed}
                type="button"
                className={replay.speed === speed ? 'active' : ''}
                onClick={() => replay.setSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="scrub">
        <span>{formatRaceTime(timeline?.start_ms ?? 0)}</span>
        <input
          type="range"
          min={timeline?.start_ms ?? 0}
          max={maxMs}
          step={10_000}
          value={Math.min(replay.atMs, maxMs)}
          disabled={!timeline}
          onChange={(event) => replay.scrub(Number(event.target.value))}
        />
        <span>{formatRaceTime(maxMs)}</span>
      </section>

      {sessionError || replay.error ? (
        <section className="empty">
          <h2>Backend not ready</h2>
          <p>{sessionError ?? replay.error}</p>
          <code>cd backend && RACELENS_FIXTURES=fixtures uvicorn racelens.api:app --port 8000</code>
        </section>
      ) : (
        <>
          <section className="summary" aria-label="Replay summary">
            <Metric label="Session time" value={formatRaceTime(replay.atMs)} />
            <Metric label="Race lap" value={`${state?.lap || '-'} / ${state?.total_laps ?? '-'}`} />
            <Metric label="Classified" value={String(state?.classification.length ?? 0)} />
            <Metric
              label="Last event"
              value={
                state?.data_quality.last_event_ms === null || state?.data_quality.last_event_ms === undefined
                  ? '-'
                  : formatRaceTime(state.data_quality.last_event_ms)
              }
            />
          </section>

          <section className="layout">
            <section className="timing-card">
              <div className="card-head">
                <div>
                  <p className="eyebrow">Timing</p>
                  <h2>{sessionId ? sessionLabel(sessionId) : 'No session'}</h2>
                </div>
                <span>
                  {replay.loading
                    ? 'Loading API state...'
                    : `${timeline?.events_total ?? 0} events / ${state?.session_status ?? 'unknown'}`}
                </span>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Pos</th>
                      <th>Driver</th>
                      <th>Laps</th>
                      <th>Last</th>
                      <th>Best</th>
                      <th>Gap</th>
                      <th>Int</th>
                      <th>Tyre</th>
                      <th>Pits</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td className="pos">{row.position ?? '-'}</td>
                        <td className="driver">{row.id}</td>
                        <td>{row.laps_completed}</td>
                        <td>{formatLapTime(row.last_lap_ms)}</td>
                        <td>{formatLapTime(row.best_lap_ms)}</td>
                        <td>{formatDeltaSeconds(row.gap_s)}</td>
                        <td>{formatDeltaSeconds(row.interval_s)}</td>
                        <td>
                          <span className={`tyre tyre-${(row.tyre_compound ?? 'unknown').toLowerCase()}`}>
                            {row.tyre_compound ?? '-'}
                            {row.tyre_age_laps !== null ? ` ${row.tyre_age_laps}L` : ''}
                          </span>
                        </td>
                        <td>{row.pit_count}</td>
                        <td>{row.in_pit ? <span className="pit">PIT</span> : 'RUN'}</td>
                      </tr>
                    ))}
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={10} className="no-data">
                          No classified cars at this timestamp.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <InsightFeed insights={replay.insights} />
          </section>
        </>
      )}
    </main>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function InsightFeed({ insights }: { insights: Insight[] }) {
  return (
    <section className="insight-feed" aria-label="Active insights">
      <div className="card-head">
        <div>
          <p className="eyebrow">Insights</p>
          <h2>What to watch</h2>
        </div>
        <span>{insights.length} active</span>
      </div>
      <div className="insight-list">
        {insights.map((insight) => (
          <article className={`insight insight-${insight.severity}`} key={insight.insight_id}>
            <p>{headline(insight)}</p>
            <span>{evidenceLine(insight)}</span>
          </article>
        ))}
        {insights.length === 0 && <p className="no-insights">No active insights</p>}
      </div>
    </section>
  )
}

const headline = (insight: Insight) => {
  const [driver, target] = insight.driver_ids
  if (insight.type.startsWith('TRAFFIC_RISK')) {
    return `${driver} stuck behind ${target}`
  }
  return insight.type.replaceAll('_', ' ')
}

const evidenceLine = (insight: Insight) => {
  const interval = insight.evidence.interval_s
  const paceDelta = insight.evidence.pace_delta_ms
  const parts = []
  if (typeof interval === 'number') parts.push(`gap ${interval.toFixed(1)}s`)
  if (typeof paceDelta === 'number') parts.push(`+${(paceDelta / 1000).toFixed(1)}s/lap faster`)
  parts.push(`${insight.confidence} confidence`)
  return parts.join(' / ')
}

createRoot(document.getElementById('root')!).render(<App />)
