import { useEffect, useRef } from 'react'
import { DriverOfDayPanel } from './DriverOfDayPanel'
import { HighlightsPanel } from './HighlightsPanel'
import type { Lang, Level } from './replayTypes'

type Props = {
  open: boolean
  onClose: () => void
  lang: Lang
  level: Level
  mode: 'replay' | 'live'
  liveAvailable: boolean
  projection: boolean
  winProb: boolean
  onLang: (lang: Lang) => void
  onLevel: (level: Level) => void
  onModeChange: (mode: 'replay' | 'live') => void
  onProjection: (value: boolean) => void
  onWinProb: (value: boolean) => void
  sessionId?: string | null
  onSeek?: (ms: number) => void
  sessionStatus?: string
  lap?: number
  totalLaps?: number | null
  atMs?: number
}

export function SettingsDrawer({
  open, onClose, lang, level, mode, liveAvailable, projection, winProb,
  onLang, onLevel, onModeChange, onProjection, onWinProb,
  sessionId, onSeek, sessionStatus, lap, totalLaps, atMs,
}: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    previousFocus.current = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !drawerRef.current) return
      const focusable = Array.from(drawerRef.current.querySelectorAll<HTMLElement>(
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
  }, [open, onClose])

  return (
    <div className={`settings-overlay${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="settings-backdrop" onClick={onClose} />
      <div ref={drawerRef} className="settings-drawer" role="dialog" aria-modal="true" aria-label="Settings">
        <div className="settings-drawer-hdr">
          <span>SETTINGS</span>
          <button ref={closeRef} type="button" className="settings-close" onClick={onClose} aria-label="Close">&#215;</button>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">MODE</div>
          <div className="tog-group">
            <button type="button" className={`tog${mode === 'replay' ? ' tog-on' : ''}`} onClick={() => { onModeChange('replay'); onClose() }}>REPLAY</button>
            <button type="button" className={`tog${mode === 'live' ? ' tog-on' : ''}`} disabled={!liveAvailable} onClick={() => { onModeChange('live'); onClose() }}>LIVE</button>
          </div>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">LANGUAGE</div>
          <div className="tog-group">
            <button type="button" className={`tog${lang === 'en' ? ' tog-on' : ''}`} onClick={() => onLang('en')}>EN</button>
            <button type="button" className={`tog${lang === 'ru' ? ' tog-on' : ''}`} onClick={() => onLang('ru')}>RU</button>
          </div>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">LEVEL</div>
          <div className="tog-group">
            <button type="button" className={`tog${level === 'beginner' ? ' tog-on' : ''}`} onClick={() => onLevel('beginner')}>ROOKIE</button>
            <button type="button" className={`tog${level === 'pro' ? ' tog-on' : ''}`} onClick={() => onLevel('pro')}>PRO</button>
          </div>
        </div>

        <div className="settings-group">
          <div className="settings-group-label">OVERLAYS</div>
          <div className="tog-group" style={{ marginBottom: 8 }}>
            <button type="button" className={`tog${projection ? ' tog-on' : ''}`} onClick={() => onProjection(!projection)}>PACE OUTLOOK</button>
          </div>
          <div className="tog-group">
            <button type="button" className={`tog${winProb ? ' tog-on' : ''}`} onClick={() => onWinProb(!winProb)}>GAP SCORE</button>
          </div>
        </div>

        {mode === 'replay' && sessionId && onSeek && (
          <div className="settings-group drawer-panels-group">
            <div className="settings-group-label">HIGHLIGHTS &amp; DOTD</div>
            <div className="drawer-panels-inner">
              <HighlightsPanel sessionId={sessionId} lang={lang} untilMs={atMs} onSeek={(ms) => { onSeek(ms); onClose() }} />
              <DriverOfDayPanel sessionId={sessionId} lang={lang} sessionStatus={sessionStatus} lap={lap} totalLaps={totalLaps} atMs={atMs} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
