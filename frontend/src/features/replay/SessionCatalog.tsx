import { useEffect, useMemo, useRef, useState } from 'react'
import { getCatalog, getPreparation, prepareSession } from '../../api/client'
import type { CatalogResponse, CatalogSession } from '../../api/types'

type Props = {
  open: boolean
  initialSeason?: number
  onClose: () => void
  onOpenReplay: (sessionId: string) => void
}

const buttonText = (session: CatalogSession) => {
  if (session.status === 'ready') return 'WATCH'
  if (session.status === 'queued') return 'QUEUED'
  if (session.status === 'failed') return 'RETRY'
  return 'PREPARE'
}

export function SessionCatalog({ open, initialSeason, onClose, onOpenReplay }: Props) {
  const [season, setSeason] = useState(initialSeason ?? new Date().getUTCFullYear())
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

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
    if (!open) return
    previousFocus.current = document.activeElement as HTMLElement | null
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('keydown', close)
      previousFocus.current?.focus()
    }
  }, [open, onClose])

  const sessions = useMemo(
    () => catalog?.events.flatMap((event) => event.sessions) ?? [],
    [catalog],
  )

  useEffect(() => {
    const queued = sessions.filter((session) => session.status === 'queued')
    if (!open || queued.length === 0) return
    const timer = window.setInterval(async () => {
      const updates = await Promise.allSettled(
        queued.map((session) => getPreparation(session.session_id)),
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
    <div className="settings-overlay open catalog-overlay">
      <button type="button" className="settings-backdrop catalog-backdrop" onClick={onClose} aria-label="Close race archive" />
      <section className="settings-drawer catalog-panel" role="dialog" aria-modal="true" aria-label="Race archive">
        <header className="settings-drawer-hdr catalog-header">
          <div>
            <small>RACE ARCHIVE · 2018—NOW</small>
            <h2>Choose any completed session</h2>
          </div>
          <button autoFocus type="button" className="settings-close" onClick={onClose} aria-label="Close">×</button>
        </header>
        <div className="catalog-toolbar">
          <label htmlFor="catalog-season">SEASON</label>
          <select id="catalog-season" value={season} onChange={(event) => setSeason(Number(event.target.value))}>
            {(catalog?.seasons ?? [season]).map((item) => <option key={item}>{item}</option>)}
          </select>
          <span>{catalog ? `${catalog.events.length} weekends` : 'Loading calendar…'}</span>
        </div>
        {error && <div className="catalog-error" role="alert">{error}</div>}
        <div className="catalog-list">
          {catalog?.events.map((event) => (
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
                    disabled={busy === session.session_id || session.status === 'queued'}
                    onClick={() => void choose(session)}
                  >
                    <span>{session.name}</span>
                    <small>{busy === session.session_id ? 'QUEUING…' : buttonText(session)}</small>
                  </button>
                ))}
              </div>
            </article>
          ))}
          {catalog && catalog.events.length === 0 && (
            <div className="catalog-empty">No completed supported sessions in this season.</div>
          )}
        </div>
      </section>
    </div>
  )
}
