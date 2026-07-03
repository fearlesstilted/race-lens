import { useEffect, useState } from 'react'
import { getDriverOfDay } from '../../api/client'
import type { DotdCandidate, DotdResponse } from '../../api/types'
import { teamColor } from './teamColors'
import { useAsync } from './useAsync'

type Lang = 'en' | 'ru'

type Props = {
  sessionId: string
  lang?: Lang
  sessionStatus?: string
  /** Current lap in progress + total, to unlock the panel in the final laps. */
  lap?: number
  totalLaps?: number | null
  /** Current session time — the pick is computed spoiler-free up to here. */
  atMs?: number
}

const DOTD_VOTE_KEY = (sessionId: string) => `racelens_dotd_vote_${sessionId}`
/** DOTD voting opens this many laps before the finish (as in real F1). */
const UNLOCK_LAPS_TO_GO = 10

function loadUserPick(sessionId: string): string | null {
  try {
    return localStorage.getItem(DOTD_VOTE_KEY(sessionId))
  } catch {
    return null
  }
}

export function DriverOfDayPanel({ sessionId, lang = 'en', sessionStatus, lap, totalLaps, atMs }: Props) {
  const [open, setOpen] = useState(false)
  const [userPick, setUserPick] = useState<string | null>(null)

  // Snapshot the pick at the moment the panel opens — spoiler-free (race so
  // far). Not live-refreshed so it doesn't churn while reading. atMs/sessionStatus
  // are deliberately excluded from deps for the same reason.
  const { data, loading } = useAsync<DotdResponse>(
    () => getDriverOfDay(sessionId, sessionStatus === 'finished' ? undefined : atMs),
    [sessionId],
    open,
  )

  useEffect(() => {
    if (!open) return
    // Load saved vote from localStorage
    setUserPick(loadUserPick(sessionId))
  }, [open, sessionId])

  // Reset on session change
  useEffect(() => {
    setUserPick(loadUserPick(sessionId))
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
  const lapsToGo = totalLaps != null && lap != null ? totalLaps - lap : null
  const available = isFinished || (lapsToGo != null && lapsToGo <= UNLOCK_LAPS_TO_GO)
  const dotdLabel = lang === 'ru'
    ? `открывается за ${UNLOCK_LAPS_TO_GO} кругов до финиша`
    : `unlocks in the final ${UNLOCK_LAPS_TO_GO} laps`
  const dotdTitle = isFinished
    ? (lang === 'ru' ? 'Гонщик дня — алгоритмический выбор' : 'Driver of the Day — algorithmic pick')
    : (lang === 'ru' ? 'Предварительный выбор — по гонке пока' : 'Provisional pick — race so far')

  return (
    <div className="dotd-wrap">
      <button
        type="button"
        className={`tog${open ? ' tog-on' : ''}`}
        onClick={() => { if (available) setOpen((v) => !v) }}
        disabled={!available}
        title={available ? dotdTitle : dotdLabel}
        style={!available ? { opacity: 0.45, cursor: 'not-allowed' } : undefined}
        aria-disabled={!available}
      >
        DOTD
      </button>
      {!available && (
        <span className="dotd-gate-hint">{dotdLabel}</span>
      )}

      {open && (
        <div className="dotd-panel">
          <div className="dotd-header">
            <span className="dotd-title">DRIVER OF THE DAY</span>
            <span className="dotd-sub">model pick · tap to vote</span>
          </div>
          <div className="dotd-footer" style={{ borderTop: 0, paddingTop: 0 }}>
            {lang === 'ru'
              ? 'Оценка: +3 за отыгранную позицию · +15 быстрейший круг · +10 камбэк (5+ поз.) · −0.5 за лишний пит'
              : 'Score: +3 per position gained · +15 fastest lap · +10 comeback (5+) · −0.5 per extra pit'}
          </div>
          {!isFinished && lapsToGo != null && (
            <div className="dotd-footer" style={{ borderTop: 0, paddingTop: 0, color: 'var(--red)' }}>
              {lang === 'ru'
                ? `предварительно — по гонке пока (осталось ${lapsToGo} кр.)`
                : `provisional — race so far (${lapsToGo} laps to go)`}
            </div>
          )}

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
