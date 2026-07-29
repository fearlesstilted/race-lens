import { useCallback, useEffect, useRef, useState } from 'react'
import { getLiveSessions } from '../../api/client'
import type { LiveSessionInfo, LiveSource } from '../../api/client'
import { TrackMap } from './TrackMap'

// ── Types ─────────────────────────────────────────────────────────────────────

type LobbyPhase = 'LOBBY' | 'SESSIONS' | 'COUNTDOWN' | 'LIVE'

type Props = {
  signalrAvailable: boolean
  onStart: (year: number, country: string, sessionName: string, source: LiveSource) => Promise<void>
  onStop: () => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseUtcMs(iso: string): number {
  // OpenF1 date_start may arrive without timezone; treat as UTC
  const s = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z'
  return Date.parse(s)
}

function formatCountdown(remainMs: number): string {
  if (remainMs <= 0) return '00:00:00'
  const totalSec = Math.floor(remainMs / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':')
}

function localTimeLabel(iso: string): string {
  const ms = parseUtcMs(iso)
  if (Number.isNaN(ms)) return iso
  return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ── Component ─────────────────────────────────────────────────────────────────

export function LiveLobby({ signalrAvailable, onStart, onStop }: Props) {
  const [phase, setPhase] = useState<LobbyPhase>('LOBBY')

  // LOBBY inputs
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [country, setCountry] = useState('')
  // signalr = free official F1 live-timing feed (default); openf1 realtime is paid.
  const [source, setSource] = useState<LiveSource>(signalrAvailable ? 'signalr' : 'openf1')
  // signalr only: FastF1 session name — no OpenF1 discovery involved.
  const [sessionName, setSessionName] = useState('Race')
  const [loadBusy, setLoadBusy] = useState(false)
  const [loadErr, setLoadErr] = useState<string | null>(null)

  // SESSIONS list
  const [sessions, setSessions] = useState<LiveSessionInfo[]>([])

  // COUNTDOWN target
  const [countdownTarget, setCountdownTarget] = useState<LiveSessionInfo | null>(null)
  const [remainMs, setRemainMs] = useState(0)
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Clear intervals on unmount
  useEffect(() => {
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current)
    }
  }, [])

  const handleLoad = useCallback(async () => {
    if (!country.trim()) { setLoadErr('Enter a country / event name'); return }
    setLoadBusy(true)
    setLoadErr(null)
    try {
      const list = await getLiveSessions(year, country.trim())
      setSessions(list)
      setPhase('SESSIONS')
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : 'Failed to load sessions')
    } finally {
      setLoadBusy(false)
    }
  }, [year, country])

  // F1 FEED path: connect straight to the official SignalR feed — no OpenF1
  // discovery (which 401/502s on race days), no session list, just start.
  const startSession = useCallback(async (name: string, nextSource: LiveSource) => {
    if (!country.trim()) { setLoadErr('Enter the Grand Prix name, e.g. Silverstone'); return }
    setLoadBusy(true)
    setLoadErr(null)
    try {
      await onStart(year, country.trim(), name, nextSource)
      setPhase('LIVE')
    } catch (error) {
      setLoadErr(error instanceof Error ? error.message : 'Failed to start live session')
    } finally {
      setLoadBusy(false)
    }
  }, [year, country, onStart])

  const handleDirectStart = useCallback(() => {
    void startSession(sessionName.trim() || 'Race', 'signalr')
  }, [sessionName, startSession])

  const handleSessionClick = useCallback((session: LiveSessionInfo) => {
    if (session.started) {
      void startSession(session.session_name, source)
    } else {
      // Enter countdown
      setCountdownTarget(session)
      const target = parseUtcMs(session.date_start)
      setRemainMs(Math.max(0, target - Date.now()))
      setPhase('COUNTDOWN')
    }
  }, [source, startSession])

  // Countdown tick + live-start polling
  useEffect(() => {
    if (phase !== 'COUNTDOWN' || !countdownTarget) return

    const target = parseUtcMs(countdownTarget.date_start)
    const tick = () => {
      const r = Math.max(0, target - Date.now())
      setRemainMs(r)
    }
    tick()
    countdownRef.current = setInterval(tick, 1000)

    return () => {
      if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null }
    }
  }, [phase, countdownTarget])

  // Also auto-start when countdown hits zero
  useEffect(() => {
    if (phase === 'COUNTDOWN' && remainMs === 0 && countdownTarget) {
      void startSession(countdownTarget.session_name, source)
    }
  }, [remainMs, phase, countdownTarget, source, startSession])

  // ── Render ─────────────────────────────────────────────────────────────────

  if (phase === 'LOBBY') {
    return (
      <main className="live-lobby">
        <section className="live-lobby-card" aria-labelledby="live-lobby-title">
          <span className="live-lobby-kicker">LIVE CAPTURE</span>
          <h1 id="live-lobby-title">Connect to F1 live timing</h1>
          <p className="live-lobby-intro">
            Start the official feed before the session. A WAITING state is normal
            until the first timing packet arrives.
          </p>
          <div className="live-lobby-controls">
            <label>
              <span>SEASON</span>
              <input
                className="live-input live-year"
                type="number"
                value={year}
                min={2018}
                max={2030}
                onChange={(event) => setYear(Number(event.target.value))}
                inputMode="numeric"
              />
            </label>
            <label>
              <span>GRAND PRIX</span>
              <input
                className="live-input live-event"
                type="text"
                value={country}
                placeholder="Belgium or Spa"
                onChange={(event) => setCountry(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && (
                  source === 'signalr' ? handleDirectStart() : void handleLoad()
                )}
              />
            </label>
            {source === 'signalr' ? (
              <>
                <label>
                  <span>SESSION</span>
                  <select
                    className="live-input live-session"
                    value={sessionName}
                    onChange={(event) => setSessionName(event.target.value)}
                  >
                    <option>Practice 1</option>
                    <option>Practice 2</option>
                    <option>Practice 3</option>
                    <option>Sprint Qualifying</option>
                    <option>Sprint</option>
                    <option>Qualifying</option>
                    <option>Race</option>
                  </select>
                </label>
                <button className="b primary" type="button" onClick={handleDirectStart} disabled={loadBusy}>
                  {loadBusy ? 'CONNECTING…' : 'START LIVE'}
                </button>
              </>
            ) : (
              <button className="b primary" type="button" onClick={handleLoad} disabled={loadBusy}>
                {loadBusy ? 'LOADING…' : 'FIND SESSIONS'}
              </button>
            )}
          </div>
          <div className="live-source-row">
            <div className="tog-group live-source-toggle" title="Live data source">
              <button
                type="button"
                className={`tog${source === 'signalr' ? ' tog-on' : ''}`}
                onClick={() => setSource('signalr')}
                disabled={!signalrAvailable}
                title="Official F1 live-timing feed — free, direct connect"
              >
                F1 FEED
              </button>
              <button
                type="button"
                className={`tog${source === 'openf1' ? ' tog-on' : ''}`}
                onClick={() => setSource('openf1')}
                title="OpenF1 API — realtime tier is paid; free tier is delayed"
              >
                OPENF1
              </button>
            </div>
            <p>
              {source === 'signalr'
                ? 'Free official feed · connects immediately and waits for the selected session.'
                : 'OpenF1 discovery · live timing may require its paid realtime tier.'}
            </p>
          </div>
          {loadErr && <div className="live-err" role="alert">{loadErr}</div>}
        </section>
        <aside className="live-lobby-guide">
          <span>BEFORE LIGHTS OUT</span>
          <strong>1 · Connect</strong>
          <p>Use the same event and session names as the F1 schedule.</p>
          <strong>2 · Leave it running</strong>
          <p>Race Lens rejects the previous session and waits for the selected one.</p>
          <strong>3 · Watch the status</strong>
          <p>WAITING becomes LIVE after the first valid timing frame.</p>
        </aside>
      </main>
    )
  }

  if (phase === 'SESSIONS') {
    return (
      <main className="live-lobby live-lobby-sessions">
        <section className="live-lobby-card">
          <div className="live-sessions-head">
            <span>
              {year} {country.toUpperCase()}
            </span>
            <button className="b" type="button" onClick={() => setPhase('LOBBY')}>
              BACK
            </button>
          </div>
          <div className="live-session-list">
            {sessions.map((s) => (
              <button
                key={s.session_key}
                type="button"
                className={`b${s.started ? ' primary' : ''}`}
                onClick={() => handleSessionClick(s)}
                disabled={loadBusy}
                title={s.started ? `Started at ${localTimeLabel(s.date_start)}` : `Starts at ${localTimeLabel(s.date_start)}`}
              >
                {s.session_name}
                <span>
                  {localTimeLabel(s.date_start)}{s.started ? '' : ' (scheduled)'}
                </span>
              </button>
            ))}
            {sessions.length === 0 && <p>No sessions found for this event.</p>}
          </div>
          {loadErr && <div className="live-err" role="alert">{loadErr}</div>}
        </section>
      </main>
    )
  }

  if (phase === 'COUNTDOWN' && countdownTarget) {
    return (
      <main className="live-countdown">
        <TrackMap
          sessionId={null}
          atMs={0}
          playing={false}
          playbackSpeed={1}
          drivers={{}}
          classification={[]}
          sessionStatus="started"
          positionsData={null}
        />
        <div className="live-countdown-overlay">
          <span>
            {countdownTarget.session_name.toUpperCase()} STARTS IN
          </span>
          <strong>
            {formatCountdown(remainMs)}
          </strong>
          <div className="live-countdown-actions">
            <button className="b" type="button" onClick={() => setPhase('SESSIONS')}>BACK</button>
            <button className="b danger" type="button" onClick={() => { setPhase('LOBBY'); onStop() }}>STOP</button>
          </div>
          <small>
            LIVE CAPTURE STARTS AT THE SCHEDULED TIME
          </small>
        </div>
      </main>
    )
  }

  // LIVE phase — render nothing here; parent has taken over
  return null
}
