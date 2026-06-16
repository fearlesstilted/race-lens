import React from 'react'
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
}

export function TopBar({ session, sessionId, sessions, lap, totalLaps, lang, level, mode, projection, winProb, onModeChange, onSessionChange, onLang, onLevel, onProjection, onWinProb, onSeek, onSettingsOpen, sessionStatus }: Props) {
  const label = sessionId ? sessionLabel(sessionId) : 'No session'
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
          <i>Near-live · OpenF1</i>
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
        <div className="tog-group tog-group--secondary">
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
        {/* PROJECTION toggle — replay only, secondary */}
        {mode === 'replay' && (
          <div className="tog-group tog-group--secondary">
            <button
              type="button"
              className={`tog${projection ? ' tog-on' : ''}`}
              onClick={() => onProjection(!projection)}
            >PROJECTION</button>
          </div>
        )}
        {/* WIN % toggle — replay only, secondary */}
        {mode === 'replay' && (
          <div className="tog-group tog-group--secondary">
            <button
              type="button"
              className={`tog${winProb ? ' tog-on' : ''}`}
              onClick={() => onWinProb(!winProb)}
            >WIN %</button>
          </div>
        )}
      </div>

      {/* HIGHLIGHTS and DOTD panels — replay only, hidden on mobile/tablet */}
      {mode === 'replay' && sessionId && onSeek && (
        <div className="top-panels">
          <HighlightsPanel sessionId={sessionId} lang={lang} onSeek={onSeek} />
          <DriverOfDayPanel sessionId={sessionId} lang={lang} sessionStatus={sessionStatus} />
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
