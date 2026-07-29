import React, { useCallback, useMemo, useRef, useState } from 'react'
import type { RaceMarker, Timeline } from '../../api/types'
import { formatRaceTime } from '../../lib/format'
import type { LivePhase } from '../../lib/liveStatus'

type Speed = 1 | 5 | 10
const SPEEDS: Speed[] = [1, 5, 10]

type Lang = 'en' | 'ru'

type Props = {
  timeline: Timeline | null
  atMs: number
  playing: boolean
  speed: Speed
  /** Wall-clock ms between stream frames — for cursor transition. */
  frameMs: number
  markers?: RaceMarker[]
  lang?: Lang
  /** Lap currently in progress, shared with the header. */
  currentLap?: number | null
  /** When false (live mode) the scrub rail is disabled and speed controls hidden. */
  canScrub?: boolean
  /** Session clock string shown in live mode (e.g. "LAP 42"). */
  liveLabel?: string | null
  livePhase?: LivePhase
  liveBadge?: string
  liveDetail?: string
  onScrub: (ms: number) => void
  onPlay: () => void
  onPause: () => void
  onSpeed: (s: Speed) => void
}

type PhaseKind = 'green' | 'red' | 'amber' | 'vsc'

type PhaseSegment = {
  kind: PhaseKind
  pct: number
  label?: string
}

function buildPhase(markers: RaceMarker[], startMs: number, endMs: number): PhaseSegment[] {
  if (endMs <= startMs) return [{ kind: 'green', pct: 100 }]

  const statusEvents: { ms: number; kind: PhaseKind; label?: string }[] = [
    { ms: startMs, kind: 'green' },
  ]

  for (const marker of markers) {
    if (marker.kind === 'RED_FLAG') statusEvents.push({ ms: marker.at_ms, kind: 'red', label: 'RF' })
    else if (marker.kind === 'VSC') statusEvents.push({ ms: marker.at_ms, kind: 'vsc', label: 'VSC' })
    else if (marker.kind === 'SAFETY_CAR') statusEvents.push({ ms: marker.at_ms, kind: 'amber', label: 'SC' })
    else if (marker.kind === 'GREEN') statusEvents.push({ ms: marker.at_ms, kind: 'green' })
  }

  statusEvents.sort((a, b) => a.ms - b.ms)
  statusEvents.push({ ms: endMs, kind: 'green' })

  const duration = endMs - startMs
  const segments: PhaseSegment[] = []

  for (let i = 0; i < statusEvents.length - 1; i++) {
    const seg = statusEvents[i]
    const next = statusEvents[i + 1]
    const segPct = ((next.ms - seg.ms) / duration) * 100
    if (segPct > 0) {
      segments.push({ kind: seg.kind, pct: segPct, label: seg.label })
    }
  }

  return segments.length > 0 ? segments : [{ kind: 'green', pct: 100 }]
}

const SPOILER_KEY = 'racelens_spoiler_free'

// ── Marker rendering helpers ──────────────────────────────────────────────────

/** Minimum gap between marker groups as fraction of total width (1.5 %). */
const CLUSTER_THRESHOLD_PCT = 1.5

type MarkerStyle = {
  color: string
  shape: 'line' | 'triangle' | 'dot' | 'chevron'
  zIndex: number
}

function markerStyle(kind: RaceMarker['kind']): MarkerStyle {
  switch (kind) {
    case 'RED_FLAG':    return { color: '#cc2222', shape: 'line',     zIndex: 5 }
    case 'SAFETY_CAR':
    case 'VSC':         return { color: '#f2a900', shape: 'line',     zIndex: 4 }
    case 'CRASH':
    case 'INCIDENT':    return { color: '#cc2222', shape: 'triangle', zIndex: 3 }
    case 'OFF_TRACK':   return { color: '#ff6a00', shape: 'triangle', zIndex: 3 }
    case 'PENALTY':     return { color: '#f2a900', shape: 'dot',      zIndex: 3 }
    case 'LEAD_CHANGE': return { color: '#ffffff', shape: 'chevron',  zIndex: 2 }
    case 'FASTEST_LAP': return { color: '#b388ff', shape: 'dot',      zIndex: 2 }
    case 'PODIUM_CHANGE': return { color: '#555566', shape: 'line',   zIndex: 1 }
    case 'OVERTAKE':    return { color: '#00d2be', shape: 'chevron',  zIndex: 2 }
    case 'UNDERCUT':    return { color: '#00d2be', shape: 'dot',      zIndex: 2 }
    default:            return { color: '#888899', shape: 'dot',      zIndex: 1 }
  }
}

/** Group close markers so they don't overlap. Returns cluster centers with merged info. */
function clusterMarkers(
  markers: RaceMarker[],
  pctFn: (m: RaceMarker) => number,
): { pct: number; items: RaceMarker[] }[] {
  if (markers.length === 0) return []
  const sorted = [...markers].sort((a, b) => a.at_ms - b.at_ms)
  const groups: { pct: number; items: RaceMarker[] }[] = []
  for (const m of sorted) {
    const pct = pctFn(m)
    const last = groups[groups.length - 1]
    if (last && pct - last.pct < CLUSTER_THRESHOLD_PCT) {
      last.items.push(m)
      // keep highest-priority item's pct (first item) — no shift needed
    } else {
      groups.push({ pct, items: [m] })
    }
  }
  return groups
}

export function ReplayDeck({ timeline, atMs, playing, speed, frameMs, markers = [], lang = 'en', currentLap = null, canScrub = true, liveLabel, livePhase = 'connecting', liveBadge = 'CONNECTING', liveDetail = 'OPENING LIVE TIMING', onScrub, onPlay, onPause, onSpeed }: Props) {
  const [spoilerFree, setSpoilerFree] = useState(() => {
    try { return localStorage.getItem(SPOILER_KEY) !== '0' } catch { return true }
  })
  const railRef = useRef<HTMLDivElement>(null)

  const startMs = timeline?.start_ms ?? 0
  const endMs = timeline?.end_ms ?? 0
  const duration = endMs - startMs || 1

  const progress = Math.min(Math.max((atMs - startMs) / duration, 0), 1)
  const cursorPct = progress * 100
  const phases = useMemo(() => {
    if (!timeline) return [{ kind: 'green' as const, pct: 100 }]
    return buildPhase(markers, startMs, endMs)
  }, [markers, startMs, endMs, timeline])

  // Marker clusters — respects spoilerFree (only show markers up to current atMs)
  const markerClusters = useMemo(() => {
    if (!timeline || duration <= 1 || markers.length === 0) return []
    const visible = spoilerFree ? markers.filter((m) => m.at_ms <= atMs) : markers
    const pctFn = (m: RaceMarker) => ((m.at_ms - startMs) / duration) * 100
    return clusterMarkers(visible, pctFn)
  }, [markers, spoilerFree, atMs, startMs, duration, timeline])

  const handleRailClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!railRef.current || !timeline || !canScrub) return
      const rect = railRef.current.getBoundingClientRect()
      const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1)
      onScrub(Math.round(startMs + ratio * duration))
    },
    [timeline, startMs, duration, onScrub, canScrub],
  )

  const toggleSpoiler = useCallback(() => {
    setSpoilerFree((v) => {
      const next = !v
      try { localStorage.setItem(SPOILER_KEY, next ? '1' : '0') } catch { /* noop */ }
      return next
    })
  }, [])

  const handleRailKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!timeline || !canScrub) return
    const step = Math.max(1000, Math.round(duration / 100))
    let next = atMs
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next -= step
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next += step
    else if (event.key === 'Home') next = startMs
    else if (event.key === 'End') next = endMs
    else return
    event.preventDefault()
    onScrub(Math.min(endMs, Math.max(startMs, next)))
  }, [atMs, canScrub, duration, endMs, onScrub, startMs, timeline])

  // Clock is race-relative: 0:00 at lights-out. During the formation lap
  // (before lights-out) show a label instead of a time.
  const lightsOutMs = timeline?.lights_out_ms ?? 0
  const inFormation = atMs < lightsOutMs
  const sessionTime = inFormation ? 'FORMATION LAP' : formatRaceTime(atMs - lightsOutMs)
  const cursorLabel = currentLap !== null ? `LAP ${currentLap} · ${sessionTime}` : sessionTime
  const cursorAnchor = cursorPct < 10 ? 'start' : cursorPct > 90 ? 'end' : 'center'

  const visiblePhases = useMemo(() => {
    if (!spoilerFree) return phases.map((seg, i) => ({ ...seg, key: i, neutral: false }))
    const result: { kind: PhaseKind; pct: number; key: number; neutral: boolean; label?: string }[] = []
    let accumulated = 0
    for (let i = 0; i < phases.length; i++) {
      const seg = phases[i]
      const segEnd = accumulated + seg.pct
      if (accumulated >= cursorPct) {
        result.push({ ...seg, key: i, neutral: true })
      } else if (segEnd > cursorPct) {
        const pastPct = cursorPct - accumulated
        const futurePct = segEnd - cursorPct
        result.push({ kind: seg.kind, pct: pastPct, key: i * 100, neutral: false, label: seg.label })
        result.push({ kind: seg.kind, pct: futurePct, key: i * 100 + 1, neutral: true, label: seg.label })
      } else {
        result.push({ ...seg, key: i, neutral: false })
      }
      accumulated = segEnd
    }
    return result
  }, [phases, spoilerFree, cursorPct])

  return (
    <div className={`deck${canScrub ? '' : ' deck-live'}`}>
      {canScrub ? (
        <div className="deck-shell">
          <button
            className={`deck-transport${playing ? ' is-playing' : ''}`}
            type="button"
            onClick={playing ? onPause : onPlay}
            disabled={!timeline}
            aria-label={playing ? 'Pause replay' : 'Play replay'}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {playing
                ? <path d="M7 5h3v14H7zm7 0h3v14h-3z" />
                : <path d="m8 5 11 7-11 7z" />}
            </svg>
            <span>{playing ? 'PAUSE' : 'PLAY'}</span>
          </button>

          <div className="deck-timeline">
            <div className="phase" aria-hidden="true">
              {visiblePhases.map((seg) => {
                let cls: string
                if (seg.neutral) {
                  cls = 'ph-neutral'
                } else if (seg.kind === 'red') {
                  cls = 'ph-r'
                } else if (seg.kind === 'amber') {
                  cls = 'ph-s'
                } else if (seg.kind === 'vsc') {
                  cls = 'ph-vsc'
                } else {
                  cls = 'ph-g'
                }
                return (
                  <i
                    key={seg.key}
                    className={cls}
                    style={{ width: `${seg.pct}%` }}
                    title={seg.label}
                  />
                )
              })}
            </div>
            <div
              className="rail"
              ref={railRef}
              onClick={handleRailClick}
              onKeyDown={handleRailKeyDown}
              role="slider"
              tabIndex={0}
              aria-label="Replay position"
              aria-valuemin={startMs}
              aria-valuemax={endMs}
              aria-valuenow={atMs}
              aria-valuetext={cursorLabel}
            >
              <div className="line" />
              <div
                className="played"
                style={{
                  width: `${progress * 100}%`,
                  transition: playing ? `width ${(frameMs / 1000).toFixed(2)}s linear` : 'none',
                }}
              />
              <div
                className="cursor"
                style={{
                  left: `${progress * 100}%`,
                  transition: playing ? `left ${(frameMs / 1000).toFixed(2)}s linear` : 'none',
                }}
              />
              <span
                className="cursor-pill"
                data-anchor={cursorAnchor}
                style={{
                  left: `${progress * 100}%`,
                  transition: playing ? `left ${(frameMs / 1000).toFixed(2)}s linear` : 'none',
                }}
              >
                {cursorLabel}
              </span>
              {markerClusters.map((cluster) => {
                // Pick the highest-priority item in cluster for rendering
                const primary = cluster.items.reduce((best, m) =>
                  markerStyle(m.kind).zIndex > markerStyle(best.kind).zIndex ? m : best,
                )
                const ms = markerStyle(primary.kind)
                const isSevere =
                  primary.kind === 'CRASH' ||
                  primary.kind === 'INCIDENT' ||
                  primary.kind === 'OFF_TRACK'
                const tipText = cluster.items
                  .map((m) => {
                    const label = lang === 'ru' ? m.text_ru : m.text_en
                    return m.lap != null ? `${label} · Lap ${m.lap}` : label
                  })
                  .join('\n')
                const handleMarkerClick = (event: React.MouseEvent) => {
                  event.stopPropagation()
                  onScrub(primary.at_ms)
                }
                const markerCls = [
                  'rail-marker',
                  isSevere ? 'rail-marker-severe' : '',
                ].filter(Boolean).join(' ')

                return (
                  <div
                    key={`m-${cluster.pct.toFixed(3)}`}
                    title={tipText}
                    onClick={handleMarkerClick}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onScrub(primary.at_ms)
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    aria-label={tipText}
                    className={markerCls}
                    style={{
                      left: `${cluster.pct}%`,
                      zIndex: ms.zIndex,
                    }}
                  >
                    {ms.shape === 'line' && (
                      <svg
                        width="2"
                        height="16"
                        viewBox="0 0 2 16"
                        style={{ display: 'block', opacity: 0.88 }}
                        aria-hidden="true"
                      >
                        <rect x="0" y="0" width="2" height="16" fill={ms.color} />
                      </svg>
                    )}
                    {ms.shape === 'triangle' && (
                      <svg
                        width="9"
                        height="8"
                        viewBox="0 0 9 8"
                        style={{ display: 'block', overflow: 'visible' }}
                        aria-hidden="true"
                      >
                        <polygon points="4.5,0 9,8 0,8" fill={ms.color} />
                      </svg>
                    )}
                    {ms.shape === 'dot' && (
                      <svg
                        width="5"
                        height="5"
                        viewBox="0 0 5 5"
                        style={{ display: 'block' }}
                        aria-hidden="true"
                      >
                        <circle cx="2.5" cy="2.5" r="2.5" fill={ms.color} />
                      </svg>
                    )}
                    {ms.shape === 'chevron' && (
                      <svg
                        width="7"
                        height="10"
                        viewBox="0 0 7 10"
                        style={{ display: 'block', opacity: 0.9 }}
                        aria-hidden="true"
                      >
                        <polyline
                          points="1,1 6,5 1,9"
                          fill="none"
                          stroke={ms.color}
                          strokeWidth="1.8"
                          strokeLinecap="square"
                          strokeLinejoin="miter"
                        />
                      </svg>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          <div className="deck-options">
            <div className="deck-speeds" aria-label="Replay speed">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`deck-speed${speed === s ? ' on' : ''}`}
                  onClick={() => onSpeed(s)}
                  aria-pressed={speed === s}
                >
                  {s}×
                </button>
              ))}
            </div>
            <div
              className="sp"
              role="switch"
              aria-checked={spoilerFree}
              tabIndex={0}
              onClick={toggleSpoiler}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  toggleSpoiler()
                }
              }}
            >
              SPOILER-FREE
              <span className={`sw${spoilerFree ? ' sw-on' : ''}`} />
            </div>
          </div>
        </div>
      ) : (
        <div className="deck-live-state" role="status">
          <span className={`live-badge live-badge--${livePhase}`}>{liveBadge}</span>
          <strong>{liveLabel ?? liveDetail}</strong>
          <small>{liveLabel ? liveDetail : 'PLAY-FORWARD · NO REPLAY SCRUB'}</small>
        </div>
      )}
    </div>
  )
}
