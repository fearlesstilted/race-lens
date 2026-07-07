import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { listSessions, liveStart, liveStatus, liveStop } from './api/client'
import type { LiveStatusResult } from './api/client'
import type { DataSource } from './api/dataSource'
import type { SessionSummary } from './api/types'
import { HighlightsPanel } from './features/replay/HighlightsPanel'
import { DriverOfDayPanel } from './features/replay/DriverOfDayPanel'
import { LiveLobby } from './features/replay/LiveLobby'
import { ForecastStrip } from './features/replay/ForecastStrip'
import { StintTimeline } from './features/replay/StintTimeline'
import { WinProbGraph } from './features/replay/WinProbGraph'
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

// ── Settings Drawer ───────────────────────────────────────────────────────────

type DrawerProps = {
  open: boolean
  onClose: () => void
  lang: string
  level: string
  mode: string
  projection: boolean
  winProb: boolean
  onLang: (l: 'en' | 'ru') => void
  onLevel: (l: 'beginner' | 'pro') => void
  onModeChange: (m: 'replay' | 'live') => void
  onProjection: (v: boolean) => void
  onWinProb: (v: boolean) => void
  // mobile-only: HIGHLIGHTS and DOTD panel triggers
  sessionId?: string | null
  onSeek?: (ms: number) => void
  drawerLang?: 'en' | 'ru'
  sessionStatus?: string
  lap?: number
  totalLaps?: number | null
  atMs?: number
}

function SettingsDrawer({ open, onClose, lang, level, mode, projection, winProb, onLang, onLevel, onModeChange, onProjection, onWinProb, sessionId, onSeek, drawerLang, sessionStatus, lap, totalLaps, atMs }: DrawerProps) {
  return (
    <div className={`settings-overlay${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="settings-backdrop" onClick={onClose} />
      <div className="settings-drawer" role="dialog" aria-label="Settings">
        <div className="settings-drawer-hdr">
          <span>SETTINGS</span>
          <button type="button" className="settings-close" onClick={onClose} aria-label="Close">&#215;</button>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">MODE</div>
          <div className="tog-group">
            <button type="button" className={`tog${mode === 'replay' ? ' tog-on' : ''}`} onClick={() => { onModeChange('replay'); onClose() }}>REPLAY</button>
            <button type="button" className={`tog${mode === 'live' ? ' tog-on' : ''}`} onClick={() => { onModeChange('live'); onClose() }}>LIVE</button>
          </div>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">LANGUAGE</div>
          <div className="tog-group">
            <button type="button" className={`tog${lang === 'en' ? ' tog-on' : ''}`} onClick={() => onLang('en')}>EN</button>
            <button type="button" className={`tog${lang === 'ru' ? ' tog-on' : ''}`} onClick={() => onLang('ru')}>RU</button>
          </div>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">LEVEL</div>
          <div className="tog-group">
            <button type="button" className={`tog${level === 'beginner' ? ' tog-on' : ''}`} onClick={() => onLevel('beginner')}>ROOKIE</button>
            <button type="button" className={`tog${level === 'pro' ? ' tog-on' : ''}`} onClick={() => onLevel('pro')}>PRO</button>
          </div>
        </div>

        {mode === 'replay' && (
          <div className="settings-group">
            <div className="settings-group-label">OVERLAYS</div>
            <div className="tog-group" style={{ marginBottom: 8 }}>
              <button type="button" className={`tog${projection ? ' tog-on' : ''}`} onClick={() => onProjection(!projection)}>PROJECTION</button>
            </div>
            <div className="tog-group">
              <button type="button" className={`tog${winProb ? ' tog-on' : ''}`} onClick={() => onWinProb(!winProb)}>WIN %</button>
            </div>
          </div>
        )}

        {/* HIGHLIGHTS and DOTD — shown in drawer on mobile/tablet (<1024px) */}
        {mode === 'replay' && sessionId && onSeek && (
          <div className="settings-group drawer-panels-group">
            <div className="settings-group-label">HIGHLIGHTS &amp; DOTD</div>
            <div className="drawer-panels-inner">
              <HighlightsPanel sessionId={sessionId} lang={drawerLang} onSeek={(ms) => { onSeek(ms); onClose() }} />
              <DriverOfDayPanel sessionId={sessionId} lang={drawerLang} sessionStatus={sessionStatus} lap={lap} totalLaps={totalLaps} atMs={atMs} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Center bottom segment tabs ────────────────────────────────────────────────

type CenterTab = 'FEED' | 'FORECAST' | 'WIN%' | 'STRATEGY'

type CenterTabsProps = {
  activeTab: CenterTab
  showForecast: boolean
  showWinProb: boolean
  showStrategy: boolean
  onTab: (t: CenterTab) => void
}

function CenterTabs({ activeTab, showForecast, showWinProb, showStrategy, onTab }: CenterTabsProps) {
  const tabs: CenterTab[] = ['FEED']
  if (showStrategy) tabs.push('STRATEGY')
  if (showForecast) tabs.push('FORECAST')
  if (showWinProb) tabs.push('WIN%')
  if (tabs.length <= 1) return null
  return (
    <div className="ctr-tabs">
      {tabs.map((t) => (
        <button
          key={t}
          type="button"
          className={`ctr-tab${activeTab === t ? ' ctr-tab-on' : ''}`}
          onClick={() => onTab(t)}
        >{t}</button>
      ))}
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

type AppMode = 'replay' | 'live'
type MobTab = 'TIMING' | 'MAP' | 'INSIGHTS' | 'FEED'
const MOB_TABS: MobTab[] = ['TIMING', 'MAP', 'INSIGHTS', 'FEED']

function App() {
  const [mode, setMode] = useState<AppMode>('replay')
  const [mobTab, setMobTab] = useState<MobTab>('MAP')
  const [settingsOpen, setSettingsOpen] = useState(false)
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
  // WIN % toggle — replay only
  const [winProb, setWinProb] = useState(false)
  // Center bottom segment tab
  const [centerTab, setCenterTab] = useState<CenterTab>('FEED')

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

  // Reattach after refresh: if the backend already runs a live session, adopt
  // it — otherwise F5 lands in the lobby and a new START just 409s.
  useEffect(() => {
    if (mode !== 'live' || isLiveActive) return
    let cancelled = false
    liveStatus()
      .then((s) => { if (!cancelled && s.is_running) setIsLiveActive(true) })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [mode, isLiveActive])

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

  const effectivePositionsData = mode === 'live' ? null : replay.positionsData

  const rows = useMemo(() => {
    if (!state) return []
    return state.classification.map((driverId) => {
      const d = state.drivers[driverId]
      return { id: driverId, ...d, position: d.rank ?? d.position }
    })
  }, [state])

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

  // Header lap = the lap IN PROGRESS (laps_completed + 1), shown once racing.
  // state.lap only counts completed laps, so without this the first lap reads "—".
  // During the formation lap (before lights-out) there is no lap number.
  const lightsOutMs = replay.timeline?.lights_out_ms ?? 0
  const racing = !!state && replay.atMs >= lightsOutMs
  let currentLap = 0
  if (racing && state) {
    const inProgress = (state.lap ?? 0) + 1
    currentLap = state.total_laps ? Math.min(inProgress, state.total_laps) : inProgress
  }

  // Build liveLabel for deck clock from current state lap
  const liveLabel = state ? `LAP ${state.lap}` : null

  return (
    <>
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        lang={replay.lang}
        level={replay.level}
        mode={mode}
        projection={projection}
        winProb={winProb}
        onLang={replay.setLang}
        onLevel={replay.setLevel}
        onModeChange={handleModeSwitch}
        onProjection={setProjection}
        onWinProb={setWinProb}
        sessionId={mode === 'replay' ? sessionId : null}
        onSeek={mode === 'replay' ? replay.scrub : undefined}
        drawerLang={replay.lang}
        sessionStatus={sessionStatus}
        lap={currentLap}
        totalLaps={state?.total_laps ?? null}
        atMs={replay.atMs}
      />
      <TopBar
        session={mode === 'replay' ? (sessions.find((s) => s.session_id === sessionId) ?? null) : null}
        sessionId={mode === 'replay' ? sessionId : null}
        sessions={mode === 'replay' ? sessions : []}
        lap={currentLap}
        totalLaps={state?.total_laps ?? null}
        lang={replay.lang}
        level={replay.level}
        mode={mode}
        projection={projection}
        winProb={winProb}
        onModeChange={handleModeSwitch}
        onSessionChange={handleSessionChange}
        onLang={replay.setLang}
        onLevel={replay.setLevel}
        onProjection={setProjection}
        onWinProb={setWinProb}
        onSeek={mode === 'replay' ? replay.scrub : undefined}
        onSettingsOpen={() => setSettingsOpen(true)}
        sessionStatus={sessionStatus}
        atMs={replay.atMs}
      />

      {mode === 'live' && !isLiveActive && (
        <LiveLobby
          onStart={async (y, c, sessionName, source) => {
            try {
              await liveStart(y, c, sessionName, 2, source)
              setIsLiveActive(true)
            } catch {
              // error is surfaced inside LiveLobby via the live/start call failure
            }
          }}
          onStop={() => { setIsLiveActive(false); setLiveStatusData(null) }}
        />
      )}
      {mode === 'live' && isLiveActive && (
        <div className="live-bar">
          <LiveStatusPill status={liveStatusData} />
          <button
            className="b danger"
            type="button"
            onClick={async () => {
              try { await liveStop() } catch { /* ignore */ }
              setIsLiveActive(false)
              setLiveStatusData(null)
            }}
          >
            STOP
          </button>
        </div>
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

      {/* Mobile tab bar — CSS shows only on <768px */}
      <div className="mob-tabbar">
        <div className="mob-tabbar-inner">
          {MOB_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`mob-tab${mobTab === tab ? ' mob-tab-on' : ''}`}
              onClick={() => setMobTab(tab)}
            >{tab}</button>
          ))}
        </div>
      </div>

      <div className="wrap" data-mob-tab={mobTab}>
        <TimingTower
          rows={rows}
          battles={replay.battles}
          selectedIds={selectedIds}
          onSelectDriver={handleSelectDriver}
        />

        <div className="col col-center">
          <TrackMap
            sessionId={mode === 'replay' ? sessionId : (state?.session_id ?? null)}
            atMs={replay.atMs}
            playing={replay.playing}
            frameMs={replay.frameMs}
            playbackSpeed={replay.speed}
            drivers={state?.drivers ?? {}}
            classification={state?.classification ?? []}
            sessionStatus={sessionStatus}
            neutralizationStartMs={replay.neutralizationStartMs}
            selectedIds={selectedIds}
            positionsData={effectivePositionsData}
            projection={mode === 'replay' && projection}
            battles={replay.battles}
            recentPasses={replay.recentPasses}
          />
          {/* Center always keeps map + tabs — selecting drivers must never hide
              forecast/win%. Driver focus moves to the right column instead. */}
          <div className="ctr-bottom">
            <CenterTabs
              activeTab={centerTab}
              showForecast={mode === 'replay' && projection}
              showWinProb={mode === 'replay' && winProb}
              showStrategy={mode === 'replay' && !!sessionId}
              onTab={setCenterTab}
            />
            <div className="ctr-pane">
              {centerTab === 'FEED' && <RaceFeed items={replay.feed} />}
              {centerTab === 'STRATEGY' && mode === 'replay' && sessionId && (
                <StintTimeline sessionId={sessionId} order={state?.classification} />
              )}
              {centerTab === 'FORECAST' && mode === 'replay' && projection && sessionId && (
                <ForecastStrip sessionId={sessionId} atMs={replay.atMs} />
              )}
              {centerTab === 'WIN%' && mode === 'replay' && winProb && sessionId && (
                <WinProbGraph sessionId={sessionId} atMs={replay.atMs} />
              )}
            </div>
          </div>
        </div>

        {/* Right column: driver focus when 1-2 selected, else insights feed. */}
        {hasFocus ? (
          <div className="col col-insights col-focus">
            <div className="label">DRIVER FOCUS</div>
            <FocusPanel
              selectedIds={selectedIds}
              drivers={state?.drivers ?? {}}
              sessionId={mode === 'replay' ? sessionId : null}
              atMs={replay.atMs}
            />
          </div>
        ) : (
          <InsightPanel
            insights={replay.insights}
            commentary={replay.commentary}
            selectedIds={selectedIds}
            sessionStatus={sessionStatus}
            sessionId={mode === 'replay' ? sessionId : null}
            atMs={replay.atMs}
          />
        )}
      </div>

      <ReplayDeck
        timeline={timeline}
        atMs={replay.atMs}
        playing={replay.playing}
        speed={replay.speed}
        frameMs={replay.frameMs}
        feed={replay.feed}
        markers={replay.markers}
        lang={replay.lang}
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
