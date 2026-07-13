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
  const [year, setYear] = useState(2026)
  const [country, setCountry] = useState('Austria')
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
      <div className="live-bar" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.375rem', padding: '0.5rem 0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          <input
            className="live-input"
            type="number"
            value={year}
            min={2018}
            max={2030}
            onChange={(e) => setYear(Number(e.target.value))}
            title="Year"
            style={{ width: '4rem' }}
          />
          <input
            className="live-input"
            type="text"
            value={country}
            placeholder="Austria"
            onChange={(e) => setCountry(e.target.value)}
            title="Country / event"
            style={{ width: '9rem' }}
            onKeyDown={(e) => e.key === 'Enter' && void handleLoad()}
          />
          {source === 'signalr' ? (
            <>
              <input
                className="live-input"
                type="text"
                value={sessionName}
                placeholder="Race"
                onChange={(e) => setSessionName(e.target.value)}
                title='Session: Race / Qualifying / Sprint / FP1…'
                style={{ width: '7rem' }}
                onKeyDown={(e) => e.key === 'Enter' && handleDirectStart()}
              />
              <button className="b primary" type="button" onClick={handleDirectStart} disabled={loadBusy}>
                {loadBusy ? '...' : 'START'}
              </button>
            </>
          ) : (
            <button className="b primary" type="button" onClick={handleLoad} disabled={loadBusy}>
              {loadBusy ? '...' : 'LOAD'}
            </button>
          )}
          <div className="tog-group" title="Live data source">
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
        </div>
        {source === 'signalr' && (
          <span style={{ color: '#666', fontSize: '0.75rem', letterSpacing: '0.08em' }}>
            прямое подключение к официальному F1 live timing — подключайся ДО старта сессии
          </span>
        )}
        {loadErr && <span className="live-err">{loadErr}</span>}
      </div>
    )
  }

  if (phase === 'SESSIONS') {
    return (
      <div className="live-bar" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.375rem', padding: '0.5rem 0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontStyle: 'italic', fontWeight: 700, letterSpacing: '0.08em', color: '#888', fontSize: '0.875rem' }}>
            {year} {country.toUpperCase()}
          </span>
          <button className="b" type="button" onClick={() => setPhase('LOBBY')} style={{ fontSize: '0.8rem' }}>
            BACK
          </button>
        </div>
        <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
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
              <span style={{ display: 'block', fontSize: '0.75rem', fontWeight: 400, opacity: 0.7 }}>
                {localTimeLabel(s.date_start)}{s.started ? '' : ' (scheduled)'}
              </span>
            </button>
          ))}
        </div>
      </div>
    )
  }

  if (phase === 'COUNTDOWN' && countdownTarget) {
    return (
      <div style={{ position: 'relative', width: '100%' }}>
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
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(10,10,14,0.82)',
          fontFamily: "'Barlow Condensed', sans-serif",
          fontStyle: 'italic',
        }}>
          <div style={{ color: '#888', fontSize: '0.875rem', letterSpacing: '0.15em', marginBottom: '0.375rem' }}>
            {countdownTarget.session_name.toUpperCase()} STARTS IN
          </div>
          <div style={{ color: '#fff', fontSize: '3.125rem', fontWeight: 900, letterSpacing: '0.06em', lineHeight: 1 }}>
            {formatCountdown(remainMs)}
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
            <button className="b" type="button" onClick={() => setPhase('SESSIONS')}>BACK</button>
            <button className="b danger" type="button" onClick={() => { setPhase('LOBBY'); onStop() }}>STOP</button>
          </div>
          <div style={{ marginTop: '0.5rem', color: '#555', fontSize: '0.75rem', letterSpacing: '0.1em' }}>
            LIVE CAPTURE STARTS AT THE SCHEDULED TIME
          </div>
        </div>
      </div>
    )
  }

  // LIVE phase — render nothing here; parent has taken over
  return null
}
