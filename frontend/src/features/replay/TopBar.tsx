import { useState } from 'react'
import type { SessionSummary } from '../../api/types'
import { sessionLabel, sessionMeta, sessionTypeLabel } from '../../lib/format'
import type { Lang, Level } from './useReplay'
import { HighlightsPanel } from './HighlightsPanel'
import { DriverOfDayPanel } from './DriverOfDayPanel'

type AppMode = 'replay' | 'live'

type Props = {
  session: SessionSummary | null
  sessionId: string | null
  sessions: SessionSummary[]
  lap: number
  totalLaps: number | null
  lang: Lang
  level: Level
  mode: AppMode
  liveAvailable: boolean
  projection: boolean
  winProb: boolean
  voice: boolean
  onModeChange: (mode: AppMode) => void
  onSessionChange: (id: string) => void
  onLang: (lang: Lang) => void
  onLevel: (level: Level) => void
  onProjection: (on: boolean) => void
  onWinProb: (on: boolean) => void
  onVoice: (on: boolean) => void
  onSeek?: (ms: number) => void
  onSettingsOpen?: () => void
  onCatalogOpen?: () => void
  sessionStatus?: string
  atMs?: number
  /** Live-only session badge text, e.g. "SILVERSTONE · RACE". */
  sessionName?: string | null
}

export function TopBar({ session, sessionId, sessions, lap, totalLaps, lang, level, mode, liveAvailable, projection, winProb, voice, onModeChange, onSessionChange, onLang, onLevel, onProjection, onWinProb, onVoice, onSeek, onSettingsOpen, onCatalogOpen, sessionStatus, atMs, sessionName }: Props) {
  const label = sessionId ? sessionLabel(sessionId) : 'No session'
  const choices = sessions.map((item) => ({ ...item, ...sessionMeta(item.session_id) }))
  const current = choices.find((item) => item.session_id === sessionId) ?? choices[0]
  const years = [...new Set(choices.map((item) => item.year))].sort().reverse()
  const events = [...new Set(choices.filter((item) => item.year === current?.year).map((item) => item.event))]
  const types = choices.filter((item) => item.year === current?.year && item.event === current?.event)
  const choose = (matches: (item: typeof choices[number]) => boolean) => {
    const next = choices.find((item) => matches(item) && item.type === current?.type)
      ?? choices.find(matches)
    if (next) onSessionChange(next.session_id)
  }
  const [layersOpen, setLayersOpen] = useState(false)
  // LAYERS badge lights up when any optional layer is active.
  const anyLayer = projection || winProb || voice || level === 'beginner'
  return (
    <div className="top">
      <div className="ident">
        <span>RACE LENS</span>
      </div>

      {mode === 'replay' ? (
        <div className="sess">
          <div className="sess-main">
            {sessions.length > 1 && current ? (
              <>
                <div className="sess-picker sess-picker--desktop">
                  <select aria-label="Season" className="sess-select sess-year" value={current.year} onChange={(event) => choose((item) => item.year === event.target.value)}>
                    {years.map((year) => <option key={year}>{year}</option>)}
                  </select>
                  <select aria-label="Grand Prix" className="sess-select sess-event" value={current.event} onChange={(event) => choose((item) => item.year === current.year && item.event === event.target.value)}>
                    {events.map((event) => <option key={event}>{event}</option>)}
                  </select>
                  <select aria-label="Session" className="sess-select sess-type" value={current.session_id} onChange={(event) => onSessionChange(event.target.value)}>
                    {types.map((item) => <option key={item.session_id} value={item.session_id}>{sessionTypeLabel(item.type)}</option>)}
                  </select>
                </div>
                <select
                  aria-label="Race session"
                  className="sess-select sess-mobile"
                  value={current.session_id}
                  onChange={(event) => onSessionChange(event.target.value)}
                >
                  {choices.map((item) => (
                    <option key={item.session_id} value={item.session_id}>
                      {item.year} · {item.event} · {sessionTypeLabel(item.type)}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <b>{label.toUpperCase()}</b>
            )}
            {onCatalogOpen && (
              <button type="button" className="catalog-open" onClick={onCatalogOpen}>
                ARCHIVE
              </button>
            )}
          </div>
          <i>{current ? sessionTypeLabel(current.type) : 'Session'} · replay · source: {session?.source ?? 'unknown'}</i>
        </div>
      ) : (
        <div className="sess">
          <b>LIVE</b>
          <i>{sessionName ? `${sessionName} · ` : 'Near-live · '}F1 feed</i>
        </div>
      )}

      <div className="top-toggles">
        {/* Mode toggle — always visible */}
        <div className="tog-group">
          <button
            type="button"
            className={`tog${mode === 'replay' ? ' tog-on' : ''}`}
            onClick={() => onModeChange('replay')}
          >REPLAY</button>
          <button
            type="button"
            className={`tog${mode === 'live' ? ' tog-on' : ''}`}
            onClick={() => onModeChange('live')}
            disabled={!liveAvailable}
            title={liveAvailable ? 'Start a live session' : 'Live capture is disabled on this deployment'}
          >LIVE</button>
        </div>
        {/* Lang toggle — secondary (hidden on tablet/mobile) */}
        <div className="tog-group tog-group--secondary">
          <button
            type="button"
            className={`tog${lang === 'en' ? ' tog-on' : ''}`}
            onClick={() => onLang('en')}
          >EN</button>
          <button
            type="button"
            className={`tog${lang === 'ru' ? ' tog-on' : ''}`}
            onClick={() => onLang('ru')}
          >RU</button>
        </div>

        {/* LAYERS popover — collects the optional view layers so the bar stays clean. */}
        <div className="tog-group tog-group--secondary layers-wrap">
          <button
            type="button"
            className={`tog${anyLayer ? ' tog-on' : ''}`}
            aria-expanded={layersOpen}
            onClick={() => setLayersOpen((o) => !o)}
          >LAYERS ▾</button>
          {layersOpen && (
            <>
              <div className="layers-backdrop" onClick={() => setLayersOpen(false)} />
              <div className="layers-pop" role="menu">
                <div className="layer-row">
                  <span className="layer-name">DETAIL</span>
                  <div className="tog-group">
                    <button
                      type="button"
                      className={`tog${level === 'beginner' ? ' tog-on' : ''}`}
                      onClick={() => onLevel('beginner')}
                    >ROOKIE</button>
                    <button
                      type="button"
                      className={`tog${level === 'pro' ? ' tog-on' : ''}`}
                      onClick={() => onLevel('pro')}
                    >PRO</button>
                  </div>
                </div>
                <button
                  type="button"
                  className={`layer-row layer-toggle${projection ? ' on' : ''}`}
                  onClick={() => onProjection(!projection)}
                >
                  <span className="layer-name">PACE OUTLOOK</span>
                  <span className="layer-state">{projection ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`layer-row layer-toggle${winProb ? ' on' : ''}`}
                  onClick={() => onWinProb(!winProb)}
                >
                  <span className="layer-name">GAP SCORE</span>
                  <span className="layer-state">{winProb ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`layer-row layer-toggle${voice ? ' on' : ''}`}
                  onClick={() => onVoice(!voice)}
                >
                  <span className="layer-name">VOICE</span>
                  <span className="layer-state">{voice ? 'ON' : 'OFF'}</span>
                </button>
                {onSettingsOpen && (
                  <button
                    type="button"
                    className="layer-row layer-toggle"
                    onClick={() => {
                      setLayersOpen(false)
                      onSettingsOpen()
                    }}
                  >
                    <span className="layer-name">CUSTOMIZE DESK</span>
                    <span className="layer-state">→</span>
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* HIGHLIGHTS and DOTD panels — replay only, hidden on mobile/tablet */}
      {mode === 'replay' && sessionId && onSeek && (
        <div className="top-panels">
          <HighlightsPanel sessionId={sessionId} lang={lang} untilMs={atMs} onSeek={onSeek} />
          <DriverOfDayPanel sessionId={sessionId} lang={lang} sessionStatus={sessionStatus} lap={lap} totalLaps={totalLaps} atMs={atMs} />
        </div>
      )}

      {/* Settings button — visible on tablet/mobile only (CSS controls display) */}
      <button
        type="button"
        className="settings-btn"
        onClick={onSettingsOpen}
        title="Settings"
        aria-label="Open settings"
      >&#9881;</button>

      <div className="lapbox">
        <span className="word">LAP</span>
        <span className="n">{lap || '—'}</span>
        <span className="of">/ {totalLaps ?? '—'}</span>
      </div>
    </div>
  )
}
