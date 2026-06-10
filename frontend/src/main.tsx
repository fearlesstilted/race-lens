import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import { RaceEvent, formatLapTime, formatRaceTime, parseJsonl, stateAt } from './replay'

type SessionOption = {
  id: string
  label: string
  jsonlUrl: string
}

const sessions: SessionOption[] = [
  {
    id: 'monaco_2024_race',
    label: '2024 Monaco Grand Prix - Race',
    jsonlUrl: '/fixtures/monaco_2024_race.jsonl',
  },
]

const quickMarks = [
  { label: 'Race start', atMs: 3_600_000 },
  { label: 'Lap 17', atMs: 7_200_000 },
  { label: 'Lap 53', atMs: 10_000_000 },
  { label: 'Finish window', atMs: 12_100_000 },
]

function App() {
  const [sessionId, setSessionId] = useState(sessions[0].id)
  const [events, setEvents] = useState<RaceEvent[]>([])
  const [atMs, setAtMs] = useState(7_200_000)
  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  const session = sessions.find((item) => item.id === sessionId) ?? sessions[0]

  useEffect(() => {
    let cancelled = false
    setLoadState('loading')
    setError(null)

    fetch(session.jsonlUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`Could not load ${session.jsonlUrl}`)
        return response.text()
      })
      .then((text) => {
        if (cancelled) return
        const parsed = parseJsonl(text)
        setEvents(parsed)
        setLoadState('ready')
        const last = parsed.at(-1)?.session_time_ms
        if (last && atMs > last) setAtMs(last)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setEvents([])
        setLoadState('error')
        setError(err instanceof Error ? err.message : 'Unknown loading error')
      })

    return () => {
      cancelled = true
    }
  }, [session.jsonlUrl])

  const maxMs = events.at(-1)?.session_time_ms ?? 12_100_000
  const state = useMemo(() => stateAt(events, atMs), [events, atMs])
  const rows = state.classification.map((driverId) => ({
    id: driverId,
    ...state.drivers[driverId],
  }))

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Race Lens</p>
          <h1>Replay timing monitor</h1>
        </div>
        <div className={`quality quality-${state.data_quality.status}`}>
          <span>{state.data_quality.status}</span>
          <strong>{state.data_quality.events_applied}</strong>
          <small>events applied</small>
        </div>
      </header>

      <section className="controls" aria-label="Replay controls">
        <label>
          Session
          <select value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
            {sessions.map((item) => (
              <option value={item.id} key={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="time-input">
          At time
          <input
            type="number"
            value={atMs}
            min={0}
            max={maxMs}
            step={10_000}
            onChange={(event) => setAtMs(Number(event.target.value))}
          />
        </label>

        <div className="quickmarks" aria-label="Quick timestamps">
          {quickMarks.map((mark) => (
            <button key={mark.label} type="button" onClick={() => setAtMs(mark.atMs)}>
              {mark.label}
            </button>
          ))}
        </div>
      </section>

      <section className="scrub">
        <span>{formatRaceTime(0)}</span>
        <input
          type="range"
          min={0}
          max={maxMs}
          step={10_000}
          value={Math.min(atMs, maxMs)}
          onChange={(event) => setAtMs(Number(event.target.value))}
        />
        <span>{formatRaceTime(maxMs)}</span>
      </section>

      {loadState === 'error' ? (
        <section className="empty">
          <h2>Fixture not found</h2>
          <p>{error}</p>
          <code>cp backend/fixtures/monaco_2024_race.jsonl frontend/public/fixtures/</code>
        </section>
      ) : (
        <>
          <section className="summary" aria-label="Replay summary">
            <Metric label="Session time" value={formatRaceTime(atMs)} />
            <Metric label="Race lap" value={`${state.lap || '—'} / ${state.total_laps ?? '—'}`} />
            <Metric label="Classified" value={String(state.classification.length)} />
            <Metric
              label="Last event"
              value={
                state.data_quality.last_event_ms === null
                  ? '—'
                  : formatRaceTime(state.data_quality.last_event_ms)
              }
            />
          </section>

          <section className="timing-card">
            <div className="card-head">
              <div>
                <p className="eyebrow">Timing</p>
                <h2>{session.label}</h2>
              </div>
              <span>{loadState === 'loading' ? 'Loading JSONL...' : `${events.length} events`}</span>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Driver</th>
                    <th>Laps</th>
                    <th>Last lap</th>
                    <th>Best lap</th>
                    <th>Tyre</th>
                    <th>Pits</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="pos">{row.position ?? '—'}</td>
                      <td className="driver">{row.id}</td>
                      <td>{row.laps_completed}</td>
                      <td>{formatLapTime(row.last_lap_ms)}</td>
                      <td>{formatLapTime(row.best_lap_ms)}</td>
                      <td>
                        <span className={`tyre tyre-${(row.tyre_compound ?? 'unknown').toLowerCase()}`}>
                          {row.tyre_compound ?? '—'}
                          {row.tyre_age_laps !== null ? ` ${row.tyre_age_laps}L` : ''}
                        </span>
                      </td>
                      <td>{row.pit_count}</td>
                      <td>{row.in_pit ? <span className="pit">PIT</span> : 'RUN'}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={8} className="no-data">
                        No classified cars at this timestamp. Try Lap 17 or later.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
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

createRoot(document.getElementById('root')!).render(<App />)
