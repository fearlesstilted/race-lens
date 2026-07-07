import { useState } from 'react'
import type { SessionSummary } from '../../api/types'
import { sessionLabel } from '../../lib/format'
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
  projection: boolean
  winProb: boolean
  onModeChange: (mode: AppMode) => void
  onSessionChange: (id: string) => void
  onLang: (lang: Lang) => void
  onLevel: (level: Level) => void
  onProjection: (on: boolean) => void
  onWinProb: (on: boolean) => void
  onSeek?: (ms: number) => void
  onSettingsOpen?: () => void
  sessionStatus?: string
  atMs?: number
  /** Live-only session badge text, e.g. "SILVERSTONE · RACE". */
  sessionName?: string | null
}

export function TopBar({ sessionId, sessions, lap, totalLaps, lang, level, mode, projection, winProb, onModeChange, onSessionChange, onLang, onLevel, onProjection, onWinProb, onSeek, onSettingsOpen, sessionStatus, atMs, sessionName }: Props) {
  const label = sessionId ? sessionLabel(sessionId) : 'No session'
  const [layersOpen, setLayersOpen] = useState(false)
  // LAYERS badge lights up when any optional layer is active.
  const anyLayer = projection || winProb || level === 'beginner'
  return (
    <div className="top">
      <div className="ident">
        <span>RACE LENS</span>
      </div>

      {mode === 'replay' ? (
        <div className="sess">
          {sessions.length > 1 ? (
            <select
              className="sess-select"
              value={sessionId ?? ''}
              onChange={(e) => onSessionChange(e.target.value)}
            >
              {sessions.map((s) => (
                <option key={s.session_id} value={s.session_id}>
                  {sessionLabel(s.session_id)}
                </option>
              ))}
            </select>
          ) : (
            <b>{label.toUpperCase()}</b>
          )}
          <i>Race · replay · source: FastF1</i>
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
                  <span className="layer-name">PROJECTION</span>
                  <span className="layer-state">{projection ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`layer-row layer-toggle${winProb ? ' on' : ''}`}
                  onClick={() => onWinProb(!winProb)}
                >
                  <span className="layer-name">WIN %</span>
                  <span className="layer-state">{winProb ? 'ON' : 'OFF'}</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* HIGHLIGHTS and DOTD panels — replay only, hidden on mobile/tablet */}
      {mode === 'replay' && sessionId && onSeek && (
        <div className="top-panels">
          <HighlightsPanel sessionId={sessionId} lang={lang} onSeek={onSeek} />
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
