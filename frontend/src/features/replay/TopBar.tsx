import React from 'react'
import type { SessionSummary } from '../../api/types'
import { sessionLabel } from '../../lib/format'
import type { Lang, Level } from './useReplay'

type Props = {
  session: SessionSummary | null
  sessionId: string | null
  sessions: SessionSummary[]
  lap: number
  totalLaps: number | null
  lang: Lang
  level: Level
  onSessionChange: (id: string) => void
  onLang: (lang: Lang) => void
  onLevel: (level: Level) => void
}

export function TopBar({ session, sessionId, sessions, lap, totalLaps, lang, level, onSessionChange, onLang, onLevel }: Props) {
  const label = sessionId ? sessionLabel(sessionId) : 'No session'
  return (
    <div className="top">
      <div className="ident">
        <span>RACE LENS</span>
      </div>
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

      <div className="top-toggles">
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
      </div>

      <div className="lapbox">
        <span className="word">LAP</span>
        <span className="n">{lap || '—'}</span>
        <span className="of">/ {totalLaps ?? '—'}</span>
      </div>
    </div>
  )
}
