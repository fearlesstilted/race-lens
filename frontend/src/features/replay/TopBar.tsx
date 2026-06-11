import React from 'react'
import type { SessionSummary } from '../../api/types'
import { sessionLabel } from '../../lib/format'

type Props = {
  session: SessionSummary | null
  sessionId: string | null
  sessions: SessionSummary[]
  lap: number
  totalLaps: number | null
  onSessionChange: (id: string) => void
}

export function TopBar({ session, sessionId, sessions, lap, totalLaps, onSessionChange }: Props) {
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
      <div className="lapbox">
        <span className="word">LAP</span>
        <span className="n">{lap || '—'}</span>
        <span className="of">/ {totalLaps ?? '—'}</span>
      </div>
    </div>
  )
}
