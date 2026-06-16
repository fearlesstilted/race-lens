import React, { useEffect, useState } from 'react'
import { getDriverOfDay } from '../../api/client'
import type { DotdCandidate, DotdResponse } from '../../api/types'
import { teamColor } from './teamColors'

type Lang = 'en' | 'ru'

type Props = {
  sessionId: string
  lang?: Lang
  sessionStatus?: string
}

const DOTD_VOTE_KEY = (sessionId: string) => `racelens_dotd_vote_${sessionId}`

export function DriverOfDayPanel({ sessionId, lang = 'en', sessionStatus }: Props) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<DotdResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [userPick, setUserPick] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    getDriverOfDay(sessionId)
      .then((r) => setData(r))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
    // Load saved vote from localStorage
    try {
      const saved = localStorage.getItem(DOTD_VOTE_KEY(sessionId))
      setUserPick(saved)
    } catch {
      setUserPick(null)
    }
  }, [open, sessionId])

  // Reset on session change
  useEffect(() => {
    setData(null)
    try {
      const saved = localStorage.getItem(DOTD_VOTE_KEY(sessionId))
      setUserPick(saved)
    } catch {
      setUserPick(null)
    }
  }, [sessionId])

  const vote = (driver: string) => {
    const next = userPick === driver ? null : driver
    setUserPick(next)
    try {
      if (next) localStorage.setItem(DOTD_VOTE_KEY(sessionId), next)
      else localStorage.removeItem(DOTD_VOTE_KEY(sessionId))
    } catch { /* noop */ }
  }

  const maxScore = data?.candidates[0]?.score ?? 1
  const isFinished = sessionStatus === 'finished'
  const dotdLabel = lang === 'ru' ? 'доступно после финиша' : 'available at the chequered flag'

  return (
    <div className="dotd-wrap">
      <button
        type="button"
        className={`tog${open ? ' tog-on' : ''}`}
        onClick={() => isFinished ? setOpen((v) => !v) : undefined}
        disabled={!isFinished}
        title={isFinished ? 'Driver of the Day — algorithmic pick' : dotdLabel}
        style={!isFinished ? { opacity: 0.45, cursor: 'not-allowed' } : undefined}
      >
        DOTD
      </button>

      {open && (
        <div className="dotd-panel">
          <div className="dotd-header">
            <span className="dotd-title">DRIVER OF THE DAY</span>
            <span className="dotd-sub">model pick · tap to vote</span>
          </div>

          {loading && <div className="dotd-empty">Loading…</div>}
          {!loading && !data && <div className="dotd-empty">No data</div>}

          {data && (
            <>
              {/* Computed pick hero */}
              {data.computed_pick && (
                <div className="dotd-hero" style={{ borderColor: teamColor(data.computed_pick) }}>
                  <span className="dotd-hero-code" style={{ color: teamColor(data.computed_pick) }}>
                    {data.computed_pick}
                  </span>
                  <span className="dotd-hero-label">MODEL PICK</span>
                  {(() => {
                    const c = data.candidates.find((x) => x.driver === data.computed_pick)
                    if (!c) return null
                    return (
                      <span className="dotd-hero-note">
                        {lang === 'ru' ? c.note_ru : c.note_en}
                      </span>
                    )
                  })()}
                </div>
              )}

              {/* Top-5 list */}
              <div className="dotd-list">
                {data.candidates.map((c: DotdCandidate) => {
                  const color = teamColor(c.driver)
                  const barPct = maxScore > 0 ? Math.max(0, (c.score / maxScore) * 100) : 0
                  const isUserVote = userPick === c.driver
                  return (
                    <button
                      key={c.driver}
                      type="button"
                      className={`dotd-row${isUserVote ? ' dotd-row-voted' : ''}`}
                      onClick={() => vote(c.driver)}
                      title={lang === 'ru' ? c.note_ru : c.note_en}
                    >
                      <span className="dotd-code" style={{ color }}>{c.driver}</span>
                      <div className="dotd-bar-wrap">
                        <div className="dotd-bar" style={{ width: `${barPct}%`, background: color }} />
                      </div>
                      <span className="dotd-score">{c.score.toFixed(1)}</span>
                      {isUserVote && <span className="dotd-check">✓ your pick</span>}
                    </button>
                  )
                })}
              </div>

              <div className="dotd-footer">
                your vote is saved locally · model pick is algorithmic
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
