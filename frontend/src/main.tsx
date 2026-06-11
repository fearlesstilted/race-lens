import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { listSessions } from './api/client'
import type { SessionSummary } from './api/types'
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

function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)

  // Driver focus: up to 2 selected IDs; survives scrub/play; resets on session change
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const prevSessionRef = useRef<string | null>(null)

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
    return () => { cancelled = true }
  }, [])

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
      if (prev.includes(id)) {
        // Deselect
        return prev.filter((x) => x !== id)
      }
      if (prev.length >= 2) {
        // Replace oldest (first) with new
        return [prev[1], id]
      }
      return [...prev, id]
    })
  }, [])

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

  const handleSessionChange = (id: string) => {
    replay.pause()
    setSessionId(id)
  }

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

  return (
    <>
      <TopBar
        session={sessions.find((s) => s.session_id === sessionId) ?? null}
        sessionId={sessionId}
        sessions={sessions}
        lap={state?.lap ?? 0}
        totalLaps={state?.total_laps ?? null}
        lang={replay.lang}
        level={replay.level}
        onSessionChange={handleSessionChange}
        onLang={replay.setLang}
        onLevel={replay.setLevel}
      />
      <StatusStrip status={sessionStatus} greenFlag={replay.greenFlag} greenFlagText={replay.greenFlagText} />
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
            sessionId={sessionId}
            atMs={replay.atMs}
            playing={replay.playing}
            frameMs={replay.frameMs}
            playbackSpeed={replay.speed}
            drivers={state?.drivers ?? {}}
            classification={state?.classification ?? []}
            sessionStatus={sessionStatus}
            selectedIds={selectedIds}
            positionsData={replay.positionsData}
          />
          {hasFocus ? (
            <>
              <FocusPanel
                selectedIds={selectedIds}
                drivers={state?.drivers ?? {}}
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
        />
      </div>

      <ReplayDeck
        timeline={timeline}
        atMs={replay.atMs}
        playing={replay.playing}
        speed={replay.speed}
        frameMs={replay.frameMs}
        feed={replay.feed}
        onScrub={replay.scrub}
        onPlay={replay.play}
        onPause={replay.pause}
        onSpeed={replay.setSpeed}
      />
    </>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
