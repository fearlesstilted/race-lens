import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { getCapabilities, listSessions, liveStart, liveStatus, liveStop } from './api/client'
import type { LiveStatusResult } from './api/client'
import type { DataSource } from './api/dataSource'
import { LiveLobby } from './features/replay/LiveLobby'
import { BattleIntelligence } from './features/replay/BattleIntelligence'
import { BroadcastOverlay } from './features/replay/BroadcastOverlay'
import { ForecastStrip } from './features/replay/ForecastStrip'
import { StintTimeline } from './features/replay/StintTimeline'
import { FocusPanel } from './features/replay/FocusPanel'
import { InsightPanel } from './features/replay/InsightPanel'
import { RaceFeed } from './features/replay/RaceFeed'
import { ReplayDeck } from './features/replay/ReplayDeck'
import { SessionCatalog } from './features/replay/SessionCatalog'
import { SettingsDrawer } from './features/replay/SettingsDrawer'
import { StatusStrip } from './features/replay/StatusStrip'
import { TimingTower } from './features/replay/TimingTower'
import { TopBar } from './features/replay/TopBar'
import { useVoiceAlerts } from './features/replay/useVoiceAlerts'
import { TrackMap } from './features/replay/TrackMap'
import { readDashboardLayout, writeDashboardLayout } from './features/replay/replayTypes'
import type { DashboardLayout } from './features/replay/replayTypes'
import { useReplay } from './features/replay/useReplay'
import { lapAtTime, sessionLabel } from './lib/format'
import { focusDriverIds } from './lib/insightFocus'
import { liveLifecycle, livePresentation } from './lib/liveStatus'
import './style.css'
import './styles/dashboard.css'
import './styles/responsive.css'
import './styles/features.css'

// ── Live status pill ──────────────────────────────────────────────────────────

function LiveStatusPill({
  presentation,
}: {
  presentation: ReturnType<typeof livePresentation>
}) {
  return (
    <>
      <span className={`live-pill live-pill-${presentation.phase}`}>
        {presentation.badge}
      </span>
      <span className="live-status-detail">{presentation.detail}</span>
    </>
  )
}

// ── Center bottom segment tabs ────────────────────────────────────────────────

type CenterTab = 'FEED' | 'PACE' | 'STRATEGY'

type CenterTabsProps = {
  activeTab: CenterTab
  showForecast: boolean
  showStrategy: boolean
  onTab: (t: CenterTab) => void
}

function CenterTabs({ activeTab, showForecast, showStrategy, onTab }: CenterTabsProps) {
  const tabs: CenterTab[] = ['FEED']
  if (showStrategy) tabs.push('STRATEGY')
  if (showForecast) tabs.push('PACE')
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
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), [])
  const initialCatalogId = initialParams.get('catalog')
  const initialSessionId = initialParams.get('session')
  const initialCatalogSeason = initialCatalogId && /^\d{4}-/.test(initialCatalogId)
    ? Number(initialCatalogId.slice(0, 4))
    : undefined
  const [mode, setMode] = useState<AppMode>('replay')
  const [mobTab, setMobTab] = useState<MobTab>('MAP')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [dashboardLayout, setDashboardLayout] = useState(readDashboardLayout)
  const [catalogOpen, setCatalogOpen] = useState(Boolean(initialCatalogId))
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId)
  const [replayPinned, setReplayPinned] = useState(Boolean(initialSessionId))
  const [sessionNotice, setSessionNotice] = useState<string | null>(null)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [backendPhase, setBackendPhase] = useState<'connecting' | 'waking' | 'ready'>('connecting')
  const [startupReady, setStartupReady] = useState(false)
  const [readonlyDeployment, setReadonlyDeployment] = useState<boolean | null>(null)
  const [isLiveActive, setIsLiveActive] = useState(false)
  const [liveStatusData, setLiveStatusData] = useState<LiveStatusResult | null>(null)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [liveStopping, setLiveStopping] = useState(false)
  const [signalrAvailable, setSignalrAvailable] = useState(false)
  const closeSettings = useCallback(() => setSettingsOpen(false), [])
  const closeCatalog = useCallback(() => setCatalogOpen(false), [])
  const handleDashboardLayout = useCallback((layout: DashboardLayout) => {
    setDashboardLayout(layout)
    writeDashboardLayout(layout)
  }, [])

  // Driver focus: up to 2 selected IDs; survives scrub/play; resets on session change
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  // PROJECTION toggle — replay only
  const [projection, setProjection] = useState(false)
  // VOICE alerts — speak flags/fastest laps/passes from the feed
  const [voice, setVoice] = useState(false)
  // Center bottom segment tab
  const [centerTab, setCenterTab] = useState<CenterTab>('FEED')

  useEffect(() => {
    if (centerTab === 'PACE' && !projection) {
      setCenterTab('FEED')
    }
  }, [centerTab, projection])

  // Build DataSource from current mode
  const source = useMemo<DataSource | null>(() => {
    if (mode === 'replay') {
      return sessionId ? { kind: 'replay', sessionId } : null
    }
    return isLiveActive ? { kind: 'live' } : null
  }, [mode, sessionId, isLiveActive])

  const replay = useReplay(source)
  useVoiceAlerts(replay.feed, voice, replay.lang, mode === 'replay' ? sessionId : 'live')

  const liveDecision = liveLifecycle(liveStatusData, {
    readonly: readonlyDeployment !== false,
    explicitReplay: replayPinned,
    attachedToLive: mode === 'live' && isLiveActive,
  })
  const liveAvailable = liveDecision.canManage || liveDecision.remoteAvailable || isLiveActive

  const adoptReplay = useCallback((id: string) => {
    replay.pause()
    setMode('replay')
    setIsLiveActive(false)
    setReplayPinned(true)
    setSelectedIds([])
    setCenterTab('FEED')
    setSessionNotice(null)
    setSessionId(id)
    setCatalogOpen(false)
    const url = new URL(window.location.href)
    url.searchParams.set('session', id)
    url.searchParams.delete('catalog')
    window.history.replaceState(null, '', url)
  }, [replay.pause])

  const adoptLive = useCallback(() => {
    replay.pause()
    setMode('live')
    setIsLiveActive(true)
    setReplayPinned(false)
    setCatalogOpen(false)
    setLiveError(null)
    setCenterTab('FEED')
    setSelectedIds([])
  }, [replay.pause])

  const loadSessions = useCallback(() => {
    let cancelled = false
    const requestedAtStart = new URLSearchParams(window.location.search).get('session')
    setSessionError(null)
    setBackendPhase('connecting')
    const wakeTimer = window.setTimeout(() => {
      if (!cancelled) setBackendPhase('waking')
    }, 1200)
    listSessions(() => setBackendPhase('waking'))
      .then((items) => {
        if (cancelled) return
        window.clearTimeout(wakeTimer)
        const requested = new URLSearchParams(window.location.search).get('session')
        if (requested !== requestedAtStart) {
          setBackendPhase('ready')
          return
        }
        const requestedSession = items.find((item) => item.session_id === requested)
        const initialSession = requestedSession?.session_id ?? null
        setSessionId((current) => (
          items.some((item) => item.session_id === current) ? current : initialSession
        ))
        if (requested && !requestedSession) {
          setSessionNotice(
            `Replay "${requested}" is unavailable · choose another session`,
          )
          const url = new URL(window.location.href)
          url.searchParams.delete('session')
          window.history.replaceState(null, '', url)
          setCatalogOpen(true)
        } else {
          setSessionNotice(null)
        }
        setBackendPhase('ready')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        window.clearTimeout(wakeTimer)
        setSessionError(err instanceof Error ? err.message : 'Could not load sessions')
      })
    return () => {
      cancelled = true
      window.clearTimeout(wakeTimer)
    }
  }, [])

  // Load replay sessions once; the bounded retry covers a sleeping free Render instance.
  useEffect(() => {
    return loadSessions()
  }, [loadSessions])

  // Resolve public/live routing before opening the catalog, so production Live
  // never flashes the replay picker on first load.
  useEffect(() => {
    let cancelled = false
    void Promise.allSettled([getCapabilities(), liveStatus()]).then(([capabilities, status]) => {
      if (cancelled) return
      const readonly = capabilities.status === 'fulfilled' ? capabilities.value.readonly : true
      setReadonlyDeployment(readonly)
      if (capabilities.status === 'fulfilled') {
        setSignalrAvailable(capabilities.value.signalr_available)
      }
      if (status.status === 'fulfilled') {
        setLiveStatusData(status.value)
        const decision = liveLifecycle(status.value, {
          readonly,
          explicitReplay: Boolean(initialSessionId),
          attachedToLive: false,
        })
        if (decision.replaySessionId) adoptReplay(decision.replaySessionId)
        else if (decision.enterLive) adoptLive()
        else if (!initialSessionId) setCatalogOpen(true)
      } else if (!initialSessionId) {
        setCatalogOpen(true)
      }
      setStartupReady(true)
    })
    return () => { cancelled = true }
  }, [adoptLive, adoptReplay, initialSessionId])

  // Public deployments keep discovering lifecycle changes; attached local Live
  // uses the same five-second poll. Failed polls retain the last truthful state.
  useEffect(() => {
    if (!startupReady || !(readonlyDeployment === true || mode === 'live' || isLiveActive)) return
    let cancelled = false
    let inFlight = false
    const poll = () => {
      if (inFlight) return
      inFlight = true
      liveStatus()
        .then((status) => {
          if (cancelled) return
          setLiveStatusData(status)
          const decision = liveLifecycle(status, {
            readonly: readonlyDeployment !== false,
            explicitReplay: replayPinned,
            attachedToLive: mode === 'live' && isLiveActive,
          })
          if (decision.replaySessionId) adoptReplay(decision.replaySessionId)
          else if (decision.enterLive) adoptLive()
        })
        .catch(() => undefined)
        .finally(() => { inFlight = false })
    }
    const id = window.setInterval(poll, 5000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [adoptLive, adoptReplay, isLiveActive, mode, readonlyDeployment, replayPinned, startupReady])

  // Esc to clear selection
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedIds([])
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleSelectDriver = useCallback((id: string) => {
    setMobTab('INSIGHTS')
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 2) return [prev[1], id]
      return [...prev, id]
    })
  }, [])

  const handleFocusDrivers = useCallback((ids: string[]) => {
    const focused = focusDriverIds(ids)
    if (focused.length === 0) return
    setSelectedIds(focused)
    setMobTab('INSIGHTS')
  }, [])

  const handleModeSwitch = (next: AppMode) => {
    if (next === mode) return
    if (next === 'live' && !liveAvailable) return
    if (next === 'live' && (liveDecision.remoteAvailable || liveStatusData?.is_running)) {
      adoptLive()
      return
    }
    replay.pause()
    setMode(next)
    setIsLiveActive(false)
    setReplayPinned(next === 'replay')
    setLiveError(null)
    setCenterTab('FEED')
    setSelectedIds([])
  }

  const handleSessionChange = (id: string) => {
    adoptReplay(id)
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
  const liveView = livePresentation(liveStatusData, state !== null, replay.error)

  if (!startupReady) {
    return (
      <div className="error-screen wake-screen" role="status" aria-live="polite">
        <div>
          <span className="wake-pulse" />
          <h2>Connecting</h2>
          <p>Checking replay and Live availability.</p>
        </div>
      </div>
    )
  }

  if (sessionError && mode === 'replay') {
    return (
      <div className="error-screen">
        <div>
          <h2>Race server is still asleep</h2>
          <p>The free demo did not wake in time. Your selected race is safe.</p>
          <button type="button" className="b" onClick={loadSessions}>RETRY</button>
          <small>{sessionError}</small>
        </div>
      </div>
    )
  }

  const hasFocus = selectedIds.length > 0

  // Replay follows the range immediately; live follows the latest stream state.
  let currentLap = 0
  if (mode === 'replay') {
    currentLap = timeline?.session_id === sessionId ? lapAtTime(timeline, replay.atMs) : 0
  } else if (state) {
    const inProgress = (state.lap ?? 0) + 1
    currentLap = state.total_laps ? Math.min(inProgress, state.total_laps) : inProgress
  }

  // Build liveLabel for deck clock from current state lap
  const liveLabel = state && currentLap > 0 ? `LAP ${currentLap}` : null
  const liveSessionName = state?.session_name ?? (
    liveStatusData?.replay_session_id ? sessionLabel(liveStatusData.replay_session_id) : null
  )

  return (
    <>
      <SessionCatalog
        open={catalogOpen}
        landing={mode === 'replay' && !sessionId}
        initialSeason={initialCatalogSeason}
        onClose={closeCatalog}
        onOpenReplay={handleSessionChange}
      />
      <SettingsDrawer
        open={settingsOpen}
        onClose={closeSettings}
        lang={replay.lang}
        level={replay.level}
        mode={mode}
        liveAvailable={liveAvailable}
        liveNowAvailable={liveDecision.showLiveNow}
        projection={projection}
        dashboardLayout={dashboardLayout}
        onLang={replay.setLang}
        onLevel={replay.setLevel}
        onModeChange={handleModeSwitch}
        onProjection={setProjection}
        onDashboardLayout={handleDashboardLayout}
        sessionId={mode === 'replay' ? sessionId : null}
        onSeek={mode === 'replay' ? replay.scrub : undefined}
        sessionStatus={sessionStatus}
        lap={currentLap}
        totalLaps={state?.total_laps ?? null}
        atMs={replay.atMs}
      />
      <TopBar
        sessionId={mode === 'replay' ? sessionId : null}
        lap={currentLap}
        totalLaps={state?.total_laps ?? null}
        lang={replay.lang}
        level={replay.level}
        mode={mode}
        liveAvailable={liveAvailable}
        liveNowAvailable={liveDecision.showLiveNow}
        projection={projection}
        voice={voice}
        onModeChange={handleModeSwitch}
        onLevel={replay.setLevel}
        onVoice={setVoice}
        onProjection={setProjection}
        onSeek={mode === 'replay' ? replay.scrub : undefined}
        onSettingsOpen={() => setSettingsOpen(true)}
        onCatalogOpen={() => setCatalogOpen(true)}
        sessionStatus={sessionStatus}
        atMs={replay.atMs}
        sessionName={mode === 'live' ? liveSessionName : null}
      />

      {liveDecision.canManage && mode === 'live' && !isLiveActive && (
        <LiveLobby
          signalrAvailable={signalrAvailable}
          onStart={async (y, c, sessionName, source) => {
            setLiveError(null)
            await liveStart(y, c, sessionName, 6, source)
            setIsLiveActive(true)
          }}
          onStop={() => { setIsLiveActive(false); setLiveStatusData(null) }}
        />
      )}
      {mode === 'live' && isLiveActive && (
        <div className="live-bar">
          <LiveStatusPill presentation={liveView} />
          {liveError && <span className="live-err">{liveError}</span>}
          {liveDecision.canManage && (
            <button
              className="b danger"
              type="button"
              disabled={liveStopping}
              onClick={async () => {
                setLiveStopping(true)
                try {
                  await liveStop()
                  setIsLiveActive(false)
                  setLiveStatusData(null)
                  setLiveError(null)
                } catch (error) {
                  setLiveError(error instanceof Error ? error.message : 'Failed to stop live session')
                } finally {
                  setLiveStopping(false)
                }
              }}
            >
              {liveStopping ? 'STOPPING…' : 'STOP'}
            </button>
          )}
        </div>
      )}

      {backendPhase !== 'ready' && mode === 'replay' && (
        <div className="error-screen wake-screen" role="status" aria-live="polite">
          <div>
            <span className="wake-pulse" />
            <h2>{backendPhase === 'waking' ? 'Waking race server' : 'Connecting'}</h2>
            <p>Free hosting may need up to a minute after inactivity.</p>
          </div>
        </div>
      )}

      {((mode === 'replay' && sessionId) || isLiveActive) && (
        <>
          <StatusStrip
            status={sessionStatus}
            lap={state?.lap ?? null}
            atMs={replay.atMs}
            neutralizationStartMs={replay.neutralizationStartMs}
            greenFlag={replay.greenFlag}
            greenFlagText={replay.greenFlagText}
          />
          {sessionNotice && (
            <div className="feed-error" role="status">{sessionNotice}</div>
          )}
          {(replay.error || replay.feedError) && (
            <div className="feed-error">{replay.error || replay.feedError}</div>
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
                >{tab === 'MAP' ? dashboardLayout.center.toUpperCase() : tab}</button>
              ))}
            </div>
          </div>

          <div
            className="wrap"
            data-mob-tab={mobTab}
            data-show-timing={dashboardLayout.timing}
            data-show-insights={dashboardLayout.insights}
            data-show-feed={dashboardLayout.feed}
          >
            <TimingTower
              rows={rows}
              battles={replay.battles}
              selectedIds={selectedIds}
              onSelectDriver={handleSelectDriver}
            />

            <div className="col col-center">
              {mode === 'replay' && (
                <BroadcastOverlay
                  atMs={replay.atMs}
                  playing={replay.playing}
                  speed={replay.speed}
                  lang={replay.lang}
                  markers={replay.markers}
                  feed={replay.feed}
                />
              )}
              <div className="center-heading">
                <span>WORKSPACE</span>
                <div className="center-switch" role="group" aria-label="Center workspace">
                  {(['battles', 'track'] as const).map((center) => (
                    <button
                      key={center}
                      type="button"
                      className={dashboardLayout.center === center ? 'on' : ''}
                      aria-pressed={dashboardLayout.center === center}
                      onClick={() => handleDashboardLayout({ ...dashboardLayout, center })}
                    >
                      {center.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              {dashboardLayout.center === 'battles' ? (
                <BattleIntelligence
                  rows={rows}
                  battles={replay.battles}
                  currentLap={currentLap}
                  totalLaps={state?.total_laps ?? null}
                  onSelectDriver={handleSelectDriver}
                />
              ) : (
                <TrackMap
                  key={mode === 'replay' ? sessionId ?? 'replay' : state?.session_id ?? 'live'}
                  sessionId={mode === 'replay' ? sessionId : (state?.session_id ?? null)}
                  atMs={replay.atMs}
                  playing={replay.playing}
                  playbackSpeed={replay.speed}
                  drivers={state?.drivers ?? {}}
                  classification={state?.classification ?? []}
                  totalLaps={state?.total_laps}
                  sessionStatus={sessionStatus}
                  neutralizationStartMs={replay.neutralizationStartMs}
                  selectedIds={selectedIds}
                  positionsData={effectivePositionsData}
                  battles={replay.battles}
                  recentPasses={replay.recentPasses}
                />
              )}
              {/* Center keeps its workspace and tabs while driver focus moves right. */}
              <div className="ctr-bottom">
                <CenterTabs
                  activeTab={centerTab}
                  showForecast={projection && (mode === 'replay' ? !!sessionId : isLiveActive)}
                  showStrategy={mode === 'replay' && !!sessionId}
                  onTab={setCenterTab}
                />
                <div className="ctr-pane">
                  {centerTab === 'FEED' && (
                    <RaceFeed
                      key={mode === 'replay' ? sessionId : 'live'}
                      items={replay.feed}
                      loading={replay.loading}
                      clockOriginMs={mode === 'replay' && timeline?.session_id === sessionId ? timeline.lights_out_ms : undefined}
                    />
                  )}
                  {centerTab === 'STRATEGY' && mode === 'replay' && sessionId && (
                    <StintTimeline sessionId={sessionId} currentLap={currentLap} order={state?.classification} />
                  )}
                  {centerTab === 'PACE' && projection && (
                    mode === 'replay'
                      ? sessionId && <ForecastStrip sessionId={sessionId} atMs={replay.atMs} />
                      : isLiveActive && <ForecastStrip live atMs={replay.atMs} />
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
                  live={mode === 'live' && isLiveActive}
                  atMs={replay.atMs}
                  lap={currentLap}
                  onStrategyRequest={mode === 'replay' ? replay.pause : undefined}
                />
              </div>
            ) : (
              <InsightPanel
                key={mode === 'replay' ? sessionId ?? 'replay' : 'live'}
                insights={mode !== 'replay' || timeline?.session_id === sessionId ? replay.insights : []}
                commentary={mode !== 'replay' || timeline?.session_id === sessionId ? replay.commentary : []}
                selectedIds={selectedIds}
                sessionStatus={sessionStatus}
                sessionId={mode === 'replay' ? sessionId : null}
                atMs={replay.atMs}
                onFocusDrivers={handleFocusDrivers}
              />
            )}
          </div>

          <ReplayDeck
            timeline={timeline}
            atMs={replay.atMs}
            playing={replay.playing}
            speed={replay.speed}
            markers={replay.markers}
            canScrub={replay.canScrub}
            liveLabel={mode === 'live' ? liveLabel : null}
            livePhase={liveView.phase}
            liveBadge={liveView.badge}
            liveDetail={liveView.detail}
            onScrub={replay.scrub}
            onPlay={replay.play}
            onPause={replay.pause}
            onSpeed={replay.setSpeed}
          />
        </>
      )}
    </>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
