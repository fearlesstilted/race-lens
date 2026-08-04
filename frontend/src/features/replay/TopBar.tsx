import { useState } from 'react'
import type { SessionSummary } from '../../api/types'
import { sessionMeta, sessionTypeLabel } from '../../lib/format'
import type { Lang, Level } from './useReplay'
import { HighlightsPanel } from './HighlightsPanel'

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
  liveAvailable: boolean
  projection: boolean
  voice: boolean
  onModeChange: (mode: AppMode) => void
  onSessionChange: (id: string) => void
  onLang: (lang: Lang) => void
  onLevel: (level: Level) => void
  onProjection: (on: boolean) => void
  onVoice: (on: boolean) => void
  onSeek?: (ms: number) => void
  onSettingsOpen?: () => void
  onCatalogOpen?: () => void
  sessionStatus?: string
  atMs?: number
  /** Live-only session badge text, e.g. "SILVERSTONE · RACE". */
  sessionName?: string | null
}

export function TopBar({ sessionId, lap, totalLaps, lang, level, mode, liveAvailable, projection, voice, onModeChange, onLevel, onProjection, onVoice, onSeek, onSettingsOpen, onCatalogOpen, atMs, sessionName }: Props) {
  const current = sessionId ? sessionMeta(sessionId) : null
  const sessionTriggerLabel = current?.year
    ? `${current.year} · ${current.event} · ${sessionTypeLabel(current.type)}`
    : 'YEAR · EVENT · SESSION'
  const [layersOpen, setLayersOpen] = useState(false)
  // LAYERS badge lights up when any optional layer is active.
  const anyLayer = projection || voice || level === 'beginner'
  return (
    <div className="top">
      <div className="ident">
        <span>RACE LENS</span>
      </div>

      {mode === 'replay' ? (
        <div className="sess">
          {onCatalogOpen && (
            <button type="button" className="catalog-open" onClick={onCatalogOpen}>
              {sessionTriggerLabel}
            </button>
          )}
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
          {liveAvailable && (
            <button
              type="button"
              className={`tog${mode === 'live' ? ' tog-on' : ''}`}
              onClick={() => onModeChange('live')}
            >LIVE</button>
          )}
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
                  <span className="layer-name">PACE OUTLOOK</span>
                  <span className="layer-state">{projection ? 'ON' : 'OFF'}</span>
                </button>
                <button
                  type="button"
                  className={`layer-row layer-toggle${voice ? ' on' : ''}`}
                  onClick={() => onVoice(!voice)}
                >
                  <span className="layer-name">VOICE</span>
                  <span className="layer-state">{voice ? 'ON' : 'OFF'}</span>
                </button>
                {onSettingsOpen && (
                  <button
                    type="button"
                    className="layer-row layer-toggle"
                    onClick={() => {
                      setLayersOpen(false)
                      onSettingsOpen()
                    }}
                  >
                    <span className="layer-name">CUSTOMIZE DESK</span>
                    <span className="layer-state">→</span>
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Highlights remain available for replay; the catalog owns session selection. */}
      {mode === 'replay' && sessionId && onSeek && (
        <div className="top-panels">
          <HighlightsPanel sessionId={sessionId} lang={lang} untilMs={atMs} onSeek={onSeek} />
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
