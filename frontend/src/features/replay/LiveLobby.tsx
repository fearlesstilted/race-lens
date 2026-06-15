import React, { useCallback, useEffect, useRef, useState } from 'react'
import { getLiveSessions, liveStatus } from '../../api/client'
import type { LiveSessionInfo } from '../../api/client'
import { TrackMap } from './TrackMap'

// ── Types ─────────────────────────────────────────────────────────────────────

type LobbyPhase = 'LOBBY' | 'SESSIONS' | 'COUNTDOWN' | 'LIVE'

type Props = {
  onStart: (year: number, country: string, sessionName: string) => void
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

export function LiveLobby({ onStart, onStop }: Props) {
  const [phase, setPhase] = useState<LobbyPhase>('LOBBY')

  // LOBBY inputs
  const [year, setYear] = useState(2026)
  const [country, setCountry] = useState('Austria')
  const [loadBusy, setLoadBusy] = useState(false)
  const [loadErr, setLoadErr] = useState<string | null>(null)

  // SESSIONS list
  const [sessions, setSessions] = useState<LiveSessionInfo[]>([])

  // COUNTDOWN target
  const [countdownTarget, setCountdownTarget] = useState<LiveSessionInfo | null>(null)
  const [remainMs, setRemainMs] = useState(0)
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Clear intervals on unmount
  useEffect(() => {
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current)
      if (pollRef.current) clearInterval(pollRef.current)
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

  const handleSessionClick = useCallback((session: LiveSessionInfo) => {
    if (session.started) {
      // Immediately start live stream
      setPhase('LIVE')
      onStart(year, country.trim(), session.session_name)
    } else {
      // Enter countdown
      setCountdownTarget(session)
      const target = parseUtcMs(session.date_start)
      setRemainMs(Math.max(0, target - Date.now()))
      setPhase('COUNTDOWN')
    }
  }, [year, country, onStart])

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

    // Poll /api/live/status every 15 s to auto-transition to LIVE when data arrives
    const poll = () => {
      liveStatus()
        .then((s) => {
          // events_total isn't in liveStatus, but poll_count > 0 and is_running means data is flowing
          if (s.is_running && s.poll_count > 0 && s.last_poll_ok) {
            setPhase('LIVE')
            onStart(year, country.trim(), countdownTarget.session_name)
          }
        })
        .catch(() => undefined)
    }
    pollRef.current = setInterval(poll, 15000)

    return () => {
      if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null }
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    }
  }, [phase, countdownTarget, year, country, onStart])

  // Also auto-start when countdown hits zero
  useEffect(() => {
    if (phase === 'COUNTDOWN' && remainMs === 0 && countdownTarget) {
      setPhase('LIVE')
      onStart(year, country.trim(), countdownTarget.session_name)
    }
  }, [remainMs, phase, countdownTarget, year, country, onStart])

  // ── Render ─────────────────────────────────────────────────────────────────

  if (phase === 'LOBBY') {
    return (
      <div className="live-bar" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.5rem', padding: '0.75rem 1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
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
          <button className="b primary" type="button" onClick={handleLoad} disabled={loadBusy}>
            {loadBusy ? '...' : 'LOAD'}
          </button>
        </div>
        {loadErr && <span className="live-err">{loadErr}</span>}
      </div>
    )
  }

  if (phase === 'SESSIONS') {
    return (
      <div className="live-bar" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.5rem', padding: '0.75rem 1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontStyle: 'italic', fontWeight: 700, letterSpacing: '0.08em', color: '#888', fontSize: '0.75rem' }}>
            {year} {country.toUpperCase()}
          </span>
          <button className="b" type="button" onClick={() => setPhase('LOBBY')} style={{ fontSize: '0.7rem' }}>
            BACK
          </button>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {sessions.map((s) => (
            <button
              key={s.session_key}
              type="button"
              className={`b${s.started ? ' primary' : ''}`}
              onClick={() => handleSessionClick(s)}
              title={s.started ? `Started at ${localTimeLabel(s.date_start)}` : `Starts at ${localTimeLabel(s.date_start)}`}
            >
              {s.session_name}
              <span style={{ display: 'block', fontSize: '0.65rem', fontWeight: 400, opacity: 0.7 }}>
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
          frameMs={1000}
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
          <div style={{ color: '#888', fontSize: '0.75rem', letterSpacing: '0.15em', marginBottom: '0.5rem' }}>
            {countdownTarget.session_name.toUpperCase()} STARTS IN
          </div>
          <div style={{ color: '#fff', fontSize: '3rem', fontWeight: 900, letterSpacing: '0.06em', lineHeight: 1 }}>
            {formatCountdown(remainMs)}
          </div>
          <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem' }}>
            <button className="b" type="button" onClick={() => setPhase('SESSIONS')}>BACK</button>
            <button className="b danger" type="button" onClick={() => { setPhase('LOBBY'); onStop() }}>STOP</button>
          </div>
          <div style={{ marginTop: '0.75rem', color: '#555', fontSize: '0.65rem', letterSpacing: '0.1em' }}>
            POLLING FOR LIVE DATA EVERY 15 S
          </div>
        </div>
      </div>
    )
  }

  // LIVE phase — render nothing here; parent has taken over
  return null
}
