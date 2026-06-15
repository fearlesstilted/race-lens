import React from 'react'
import type { SessionSummary } from '../../api/types'
import { sessionLabel } from '../../lib/format'
import type { Lang, Level } from './useReplay'

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
  onModeChange: (mode: AppMode) => void
  onSessionChange: (id: string) => void
  onLang: (lang: Lang) => void
  onLevel: (level: Level) => void
  onProjection: (on: boolean) => void
}

export function TopBar({ session, sessionId, sessions, lap, totalLaps, lang, level, mode, projection, onModeChange, onSessionChange, onLang, onLevel, onProjection }: Props) {
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
        {/* Mode toggle */}
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
        {/* Lang toggle */}
        <div className="tog-group">
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
        {/* PROJECTION toggle — replay only */}
        {mode === 'replay' && (
          <div className="tog-group">
            <button
              type="button"
              className={`tog${projection ? ' tog-on' : ''}`}
              onClick={() => onProjection(!projection)}
            >PROJECTION</button>
          </div>
        )}
      </div>

      <div className="lapbox">
        <span className="word">LAP</span>
        <span className="n">{lap || '—'}</span>
        <span className="of">/ {totalLaps ?? '—'}</span>
      </div>
    </div>
  )
}
