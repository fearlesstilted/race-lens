import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { listSessions, liveStart, liveStatus, liveStop } from './api/client'
import type { LiveStatusResult } from './api/client'
import type { DataSource } from './api/dataSource'
import type { SessionSummary } from './api/types'
import { ForecastStrip } from './features/replay/ForecastStrip'
import { FocusPanel } from './features/replay/FocusPanel'
import { InsightPanel } from './features/replay/InsightPanel'
import { RaceFeed } from './features/replay/RaceFeed'
import { ReplayDeck } from './features/replay/ReplayDeck'
import { StatusStrip } from './features/replay/StatusStrip'
import { TimingTower } from './features/replay/TimingTower'
import { TopBar } from './features/replay/TopBar'
import { TrackMap } from './features/replay/TrackMap'
import { useReplay } from './features/replay/useReplay'
import './style.css'

// ── Live status pill ──────────────────────────────────────────────────────────

function LiveStatusPill({ status }: { status: LiveStatusResult | null }) {
  if (!status) return null
  const q = status.data_quality
  const cls = q === 'good' ? 'live-pill-good' : q === 'degraded' ? 'live-pill-warn' : 'live-pill-bad'
  return (
    <span className={`live-pill ${cls}`}>
      {q.toUpperCase()} · poll #{status.poll_count}
    </span>
  )
}

// ── Live form ─────────────────────────────────────────────────────────────────

type LiveFormProps = {
  onStarted: () => void
  onStopped: () => void
  isLiveActive: boolean
  liveStatus: LiveStatusResult | null
}

function LiveForm({ onStarted, onStopped, isLiveActive, liveStatus: statusData }: LiveFormProps) {
  const [year, setYear] = useState(2026)
  const [country, setCountry] = useState('')
  const [session, setSession] = useState('Race')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const handleStart = async () => {
    if (!country.trim()) { setErr('Enter a country/event name'); return }
    setBusy(true)
    setErr(null)
    try {
      await liveStart(year, country.trim(), session)
      onStarted()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to start live session')
    } finally {
      setBusy(false)
    }
  }

  const handleStop = async () => {
    setBusy(true)
    setErr(null)
    try {
      await liveStop()
      onStopped()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to stop')
    } finally {
      setBusy(false)
    }
  }

  if (isLiveActive) {
    return (
      <div className="live-bar">
        <LiveStatusPill status={statusData} />
        <button className="b danger" type="button" onClick={handleStop} disabled={busy}>STOP</button>
        {err && <span className="live-err">{err}</span>}
      </div>
    )
  }

  return (
    <div className="live-bar">
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
        style={{ width: '8rem' }}
        onKeyDown={(e) => e.key === 'Enter' && void handleStart()}
      />
      <input
        className="live-input"
        type="text"
        value={session}
        placeholder="Race"
        onChange={(e) => setSession(e.target.value)}
        title="Session type"
        style={{ width: '5rem' }}
      />
      <button className="b primary" type="button" onClick={handleStart} disabled={busy}>
        {busy ? '…' : 'START'}
      </button>
      {err && <span className="live-err">{err}</span>}
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

type AppMode = 'replay' | 'live'

function App() {
  const [mode, setMode] = useState<AppMode>('replay')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [isLiveActive, setIsLiveActive] = useState(false)
  const [liveStatusData, setLiveStatusData] = useState<LiveStatusResult | null>(null)

  // Driver focus: up to 2 selected IDs; survives scrub/play; resets on session change
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const prevSessionRef = useRef<string | null>(null)

  // PROJECTION toggle — replay only, persisted in sessionStorage
  const [projection, setProjection] = useState(false)

  // Build DataSource from current mode
  const source = useMemo<DataSource | null>(() => {
    if (mode === 'replay') {
      return sessionId ? { kind: 'replay', sessionId } : null
    }
    return isLiveActive ? { kind: 'live' } : null
  }, [mode, sessionId, isLiveActive])

  const replay = useReplay(source)

  // Load replay sessions list once
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
    return () => { cancelled = true }
  }, [])

  // Poll live status every 5 s when live is active
  useEffect(() => {
    if (!isLiveActive) { setLiveStatusData(null); return }
    let cancelled = false
    const poll = () => {
      liveStatus()
        .then((s) => { if (!cancelled) setLiveStatusData(s) })
        .catch(() => undefined)
    }
    poll()
    const id = window.setInterval(poll, 5000)
    return () => { cancelled = true; clearInterval(id) }
  }, [isLiveActive])

  // Reset selection when session changes
  useEffect(() => {
    if (sessionId !== prevSessionRef.current) {
      setSelectedIds([])
      prevSessionRef.current = sessionId
    }
  }, [sessionId])

  // Esc to clear selection
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedIds([])
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleSelectDriver = useCallback((id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 2) return [prev[1], id]
      return [...prev, id]
    })
  }, [])

  const handleModeSwitch = (next: AppMode) => {
    if (next === mode) return
    replay.pause()
    setMode(next)
    setIsLiveActive(false)
    setLiveStatusData(null)
  }

  const handleSessionChange = (id: string) => {
    replay.pause()
    setSessionId(id)
  }

  const state = replay.state
  const timeline = replay.timeline

  const rows = useMemo(
    () =>
      state?.classification.map((driverId) => ({
        id: driverId,
        ...state.drivers[driverId],
      })) ?? [],
    [state],
  )

  const sessionStatus = state?.session_status ?? 'started'

  if (sessionError) {
    return (
      <div className="error-screen">
        <div>
          <h2>Backend not ready</h2>
          <p>{sessionError}</p>
          <code>cd backend &amp;&amp; RACELENS_FIXTURES=fixtures uvicorn racelens.api:app --port 8000</code>
        </div>
      </div>
    )
  }

  const hasFocus = selectedIds.length > 0

  // Build liveLabel for deck clock from current state lap
  const liveLabel = state ? `LAP ${state.lap}` : null

  // In live mode, positionsData is always null → TrackMap uses dead-reckoning schematic
  const effectivePositionsData = mode === 'live' ? null : replay.positionsData

  return (
    <>
      <TopBar
        session={mode === 'replay' ? (sessions.find((s) => s.session_id === sessionId) ?? null) : null}
        sessionId={mode === 'replay' ? sessionId : null}
        sessions={mode === 'replay' ? sessions : []}
        lap={state?.lap ?? 0}
        totalLaps={state?.total_laps ?? null}
        lang={replay.lang}
        level={replay.level}
        mode={mode}
        projection={projection}
        onModeChange={handleModeSwitch}
        onSessionChange={handleSessionChange}
        onLang={replay.setLang}
        onLevel={replay.setLevel}
        onProjection={setProjection}
      />

      {mode === 'live' && (
        <LiveForm
          isLiveActive={isLiveActive}
          liveStatus={liveStatusData}
          onStarted={() => setIsLiveActive(true)}
          onStopped={() => { setIsLiveActive(false); setLiveStatusData(null) }}
        />
      )}

      <StatusStrip
        status={sessionStatus}
        lap={state?.lap ?? null}
        atMs={replay.atMs}
        neutralizationStartMs={replay.neutralizationStartMs}
        greenFlag={replay.greenFlag}
        greenFlagText={replay.greenFlagText}
      />
      {replay.feedError && (
        <div className="feed-error">{replay.feedError}</div>
      )}

      <div className="wrap">
        <TimingTower
          rows={rows}
          battles={replay.battles}
          selectedIds={selectedIds}
          onSelectDriver={handleSelectDriver}
          liveGaps={replay.liveGaps}
        />

        <div className="col col-center">
          <TrackMap
            sessionId={mode === 'replay' ? sessionId : null}
            atMs={replay.atMs}
            playing={replay.playing}
            frameMs={replay.frameMs}
            playbackSpeed={replay.speed}
            drivers={state?.drivers ?? {}}
            classification={state?.classification ?? []}
            sessionStatus={sessionStatus}
            selectedIds={selectedIds}
            positionsData={effectivePositionsData}
            projection={mode === 'replay' && projection}
          />
          {mode === 'replay' && projection && sessionId && (
            <ForecastStrip sessionId={sessionId} atMs={replay.atMs} />
          )}
          {hasFocus ? (
            <>
              <FocusPanel
                selectedIds={selectedIds}
                drivers={state?.drivers ?? {}}
                sessionId={mode === 'replay' ? sessionId : null}
                atMs={replay.atMs}
              />
              <RaceFeed items={replay.feed.slice(-4)} compact />
            </>
          ) : (
            <RaceFeed items={replay.feed} />
          )}
        </div>

        <InsightPanel
          insights={replay.insights}
          commentary={replay.commentary}
          selectedIds={selectedIds}
          sessionStatus={sessionStatus}
          sessionId={mode === 'replay' ? sessionId : null}
          atMs={replay.atMs}
        />
      </div>

      <ReplayDeck
        timeline={timeline}
        atMs={replay.atMs}
        playing={replay.playing}
        speed={replay.speed}
        frameMs={replay.frameMs}
        feed={replay.feed}
        canScrub={replay.canScrub}
        liveLabel={mode === 'live' ? liveLabel : null}
        onScrub={replay.scrub}
        onPlay={replay.play}
        onPause={replay.pause}
        onSpeed={replay.setSpeed}
      />
    </>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
