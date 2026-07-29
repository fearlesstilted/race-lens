import { useEffect, useMemo, useRef, useState } from 'react'
import { getCatalog, getPreparation, prepareSession } from '../../api/client'
import type { CatalogResponse, CatalogSession, CatalogSessionType } from '../../api/types'

type Props = {
  open: boolean
  landing?: boolean
  initialSeason?: number
  onClose: () => void
  onOpenReplay: (sessionId: string) => void
}

const buttonText = (session: CatalogSession) => {
  if (session.status === 'ready') return 'WATCH'
  if (session.status === 'queued') return 'QUEUED'
  if (session.status === 'processing') return 'PROCESSING'
  if (session.status === 'failed') return 'RETRY'
  return 'PREPARE'
}

const SESSION_TYPES: Array<'ALL' | CatalogSessionType> = [
  'ALL', 'FP1', 'FP2', 'FP3', 'SQ', 'Sprint', 'Q', 'R',
]

export function SessionCatalog({ open, landing = false, initialSeason, onClose, onOpenReplay }: Props) {
  const [season, setSeason] = useState(initialSeason ?? new Date().getUTCFullYear())
  const [sessionType, setSessionType] = useState<'ALL' | CatalogSessionType>('ALL')
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const previousFocus = useRef<HTMLElement | null>(null)
  const panel = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setCatalog(null)
    setError(null)
    getCatalog(season)
      .then((value) => { if (!cancelled) setCatalog(value) })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not load race catalog')
      })
    return () => { cancelled = true }
  }, [open, season])

  useEffect(() => {
    if (!open || landing) return
    previousFocus.current = document.activeElement as HTMLElement | null
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !panel.current) return
      const focusable = Array.from(panel.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
      ))
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => {
      window.removeEventListener('keydown', handleKey)
      previousFocus.current?.focus()
    }
  }, [landing, open, onClose])

  const sessions = useMemo(
    () => catalog?.events.flatMap((event) => event.sessions) ?? [],
    [catalog],
  )
  const events = useMemo(
    () => catalog?.events.flatMap((event) => {
      const matching = sessionType === 'ALL'
        ? event.sessions
        : event.sessions.filter((session) => session.type === sessionType)
      return matching.length ? [{ ...event, sessions: matching }] : []
    }) ?? [],
    [catalog, sessionType],
  )

  useEffect(() => {
    const active = sessions.filter(
      (session) => session.status === 'queued' || session.status === 'processing',
    )
    if (!open || active.length === 0) return
    const timer = window.setInterval(async () => {
      const updates = await Promise.allSettled(
        active.map((session) => getPreparation(session.session_id)),
      )
      setCatalog((current) => {
        if (!current) return current
        const byId = new Map(
          updates.flatMap((update) => update.status === 'fulfilled'
            ? [[update.value.session_id, update.value] as const]
            : []),
        )
        return {
          ...current,
          events: current.events.map((event) => ({
            ...event,
            sessions: event.sessions.map((session) => {
              const update = byId.get(session.session_id)
              return update ? {
                ...session,
                status: update.status,
                replay_session_id: update.replay_session_id,
              } : session
            }),
          })),
        }
      })
    }, 5000)
    return () => window.clearInterval(timer)
  }, [open, sessions])

  if (!open) return null

  const choose = async (session: CatalogSession) => {
    if (session.replay_session_id) {
      onOpenReplay(session.replay_session_id)
      onClose()
      return
    }
    if (!catalog?.preparation_enabled) {
      setError('This public demo cannot build new archives yet. Run the recorder locally or enable worker storage.')
      return
    }
    setBusy(session.session_id)
    setError(null)
    try {
      const job = await prepareSession(session.session_id)
      setCatalog((current) => current && ({
        ...current,
        events: current.events.map((event) => ({
          ...event,
          sessions: event.sessions.map((item) => item.session_id === session.session_id
            ? { ...item, status: job.status, replay_session_id: job.replay_session_id }
            : item),
        })),
      }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not queue this session')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className={`settings-overlay open catalog-overlay${landing ? ' catalog-landing' : ''}`}>
      {!landing && (
        <button type="button" className="settings-backdrop catalog-backdrop" onClick={onClose} aria-label="Close race archive" />
      )}
      <section
        ref={panel}
        className="settings-drawer catalog-panel"
        role={landing ? 'main' : 'dialog'}
        aria-modal={landing ? undefined : true}
        aria-label="Race archive"
      >
        <header className="settings-drawer-hdr catalog-header">
          <div>
            <small>RACE ARCHIVE · 2018—NOW</small>
            <h2>{landing ? 'Choose a session to begin' : 'Choose any completed session'}</h2>
          </div>
          {!landing && (
            <button autoFocus type="button" className="settings-close" onClick={onClose} aria-label="Close">×</button>
          )}
        </header>
        <div className="catalog-toolbar">
          <label htmlFor="catalog-season">SEASON</label>
          <select id="catalog-season" value={season} onChange={(event) => setSeason(Number(event.target.value))}>
            {(catalog?.seasons ?? [season]).map((item) => <option key={item}>{item}</option>)}
          </select>
          <label htmlFor="catalog-session-type">TYPE</label>
          <select
            id="catalog-session-type"
            value={sessionType}
            onChange={(event) => setSessionType(event.target.value as 'ALL' | CatalogSessionType)}
          >
            {SESSION_TYPES.map((item) => <option key={item}>{item}</option>)}
          </select>
          <span>{catalog ? `${events.length} weekends` : 'Loading calendar…'}</span>
        </div>
        <div className="catalog-notice">
          Missing sessions are prepared once by the archive worker. A full archive often takes 15–45 minutes; queued requests can take longer.
        </div>
        {error && <div className="catalog-error" role="alert" aria-live="polite">{error}</div>}
        <div className="catalog-list" aria-busy={!catalog}>
          {events.map((event) => (
            <article className="catalog-event" key={event.round}>
              <div className="catalog-event-name">
                <small>ROUND {String(event.round).padStart(2, '0')}</small>
                <b>{event.name}</b>
              </div>
              <div className="catalog-sessions">
                {event.sessions.map((session) => (
                  <button
                    type="button"
                    className={`catalog-session is-${session.status}`}
                    key={session.session_id}
                    disabled={
                      busy !== null
                      || session.status === 'queued'
                      || session.status === 'processing'
                    }
                    onClick={() => void choose(session)}
                  >
                    <span>{session.name}</span>
                    <small>{busy === session.session_id ? 'QUEUING…' : buttonText(session)}</small>
                  </button>
                ))}
              </div>
            </article>
          ))}
          {catalog && events.length === 0 && (
            <div className="catalog-empty">No completed supported sessions in this season.</div>
          )}
        </div>
      </section>
    </div>
  )
}
