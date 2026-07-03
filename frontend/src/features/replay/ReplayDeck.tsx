import React, { useCallback, useMemo, useRef, useState } from 'react'
import type { FeedItem, RaceMarker, Timeline } from '../../api/types'
import { formatRaceTime } from '../../lib/format'

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
  feed: FeedItem[]
  markers?: RaceMarker[]
  lang?: Lang
  /** When false (live mode) the scrub rail is disabled and speed controls hidden. */
  canScrub?: boolean
  /** Session clock string shown in live mode (e.g. "LAP 42"). */
  liveLabel?: string | null
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

function buildPhase(feed: FeedItem[], startMs: number, endMs: number): PhaseSegment[] {
  if (endMs <= startMs) return [{ kind: 'green', pct: 100 }]

  const statusEvents: { ms: number; kind: PhaseKind; label?: string }[] = [
    { ms: startMs, kind: 'green' },
  ]

  for (const item of feed) {
    const txt = item.text.toLowerCase()
    if (item.kind === 'red_flag' || (item.kind === 'status' && txt.includes('red flag'))) {
      statusEvents.push({ ms: item.at_ms, kind: 'red', label: 'RF' })
    } else if (txt.includes('virtual safety car') || txt.includes('vsc')) {
      statusEvents.push({ ms: item.at_ms, kind: 'vsc', label: 'VSC' })
    } else if (item.kind === 'safety_car' || txt.includes('safety car')) {
      statusEvents.push({ ms: item.at_ms, kind: 'amber', label: 'SC' })
    } else if (item.kind === 'green_flag' || txt.includes('green flag') || txt.includes('race resumed')) {
      statusEvents.push({ ms: item.at_ms, kind: 'green' })
    }
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

function lapFromTimeline(timeline: Timeline, atMs: number): number | null {
  let lap: number | null = null
  for (const [lapStr, lapMs] of Object.entries(timeline.lap_marks)) {
    if (lapMs <= atMs) {
      const n = parseInt(lapStr, 10)
      if (lap === null || n > lap) lap = n
    }
  }
  return lap
}

/** Compute lap label positions at every 10 laps from timeline.lap_marks */
function buildLapLabels(
  timeline: Timeline,
  startMs: number,
  duration: number,
): { lap: number; pct: number }[] {
  const result: { lap: number; pct: number }[] = []
  for (const [lapStr, lapMs] of Object.entries(timeline.lap_marks)) {
    const lap = parseInt(lapStr, 10)
    if (lap % 10 !== 0) continue
    const pct = ((lapMs - startMs) / duration) * 100
    if (pct >= 0 && pct <= 100) result.push({ lap, pct })
  }
  return result.sort((a, b) => a.lap - b.lap)
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

export function ReplayDeck({ timeline, atMs, playing, speed, frameMs, feed, markers = [], lang = 'en', canScrub = true, liveLabel, onScrub, onPlay, onPause, onSpeed }: Props) {
  const [spoilerFree, setSpoilerFree] = useState(() => {
    try { return localStorage.getItem(SPOILER_KEY) === '1' } catch { return false }
  })
  const railRef = useRef<HTMLDivElement>(null)

  const startMs = timeline?.start_ms ?? 0
  const endMs = timeline?.end_ms ?? 0
  const duration = endMs - startMs || 1

  const progress = Math.min(Math.max((atMs - startMs) / duration, 0), 1)
  const cursorPct = progress * 100
  const currentLap = timeline ? lapFromTimeline(timeline, atMs) : null

  const phases = useMemo(() => {
    if (!timeline) return [{ kind: 'green' as const, pct: 100 }]
    return buildPhase(feed, startMs, endMs)
  }, [feed, startMs, endMs, timeline])

  const lapLabels = useMemo(() => {
    if (!timeline || duration <= 1) return []
    return buildLapLabels(timeline, startMs, duration)
  }, [timeline, startMs, duration])

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

  // Clock is race-relative: 0:00 at lights-out. During the formation lap
  // (before lights-out) show a label instead of a time.
  const lightsOutMs = timeline?.lights_out_ms ?? 0
  const inFormation = atMs < lightsOutMs
  const sessionTime = inFormation ? 'FORMATION LAP' : formatRaceTime(atMs - lightsOutMs)
  const totalTime = formatRaceTime(Math.max(0, endMs - lightsOutMs))

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
    <div className="deck">
      {/* Phase strip — flush above rail */}
      <div className="phase">
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
      {/* Timeline rail */}
      <div className={`rail${canScrub ? '' : ' rail-disabled'}`} ref={railRef} onClick={handleRailClick}>
        <div className="line" />
        <div
          className="played"
          style={{
            width: `${progress * 100}%`,
            transition: playing ? `width ${(frameMs / 1000).toFixed(2)}s linear` : 'none',
          }}
        />
        {/* Lap labels every 10 laps */}
        {lapLabels
          .filter((ll) => !spoilerFree || ll.pct <= cursorPct)
          .map(({ lap, pct }) => (
            <div key={lap} className="lap-label" style={{ left: `${pct}%` }}>
              L{lap}
            </div>
          ))}
        <div
          className="cursor"
          style={{
            left: `${progress * 100}%`,
            transition: playing ? `left ${(frameMs / 1000).toFixed(2)}s linear` : 'none',
          }}
          data-lap={currentLap !== null ? `LAP ${currentLap}` : ''}
        />
        {/* Race markers */}
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
          const handleMarkerClick = (e: React.MouseEvent) => {
            e.stopPropagation()
            if (canScrub) onScrub(primary.at_ms)
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
              className={markerCls}
              style={{
                left: `${cluster.pct}%`,
                zIndex: ms.zIndex,
                cursor: canScrub ? 'pointer' : 'default',
              }}
            >
              {ms.shape === 'line' && (
                /* Flag line: crisp 2px vertical bar, full rail height */
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
                /* Proper equilateral-ish triangle pointing up.
                   Base 9px, height 8px — optically balanced at this scale. */
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
                /* Filled circle — clean at 5px diameter */
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
                /* Right-pointing chevron: a real SVG path, not a character */
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
      {/* Single control row: play/speeds left, spoiler+time right */}
      <div className="deckrow">
        {canScrub ? (
          <>
            {playing ? (
              <button className="b primary" type="button" onClick={onPause}>
                PAUSE
              </button>
            ) : (
              <button className="b primary" type="button" onClick={onPlay} disabled={!timeline}>
                PLAY
              </button>
            )}
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                className={`b${speed === s ? ' on' : ''}`}
                onClick={() => onSpeed(s)}
              >
                {s}×
              </button>
            ))}
            <div className="sp" role="button" tabIndex={0} onClick={toggleSpoiler} onKeyDown={(e) => e.key === 'Enter' && toggleSpoiler()}>
              SPOILER-FREE
              <span className={`sw${spoilerFree ? ' sw-on' : ''}`} aria-checked={spoilerFree} role="switch" />
            </div>
            <span className="clock">
              <small>SESSION</small>
              {inFormation || spoilerFree ? sessionTime : `${sessionTime} / ${totalTime}`}
            </span>
          </>
        ) : (
          <>
            <span className="live-badge">● LIVE</span>
            {liveLabel && <span className="clock"><small>SESSION</small>{liveLabel}</span>}
          </>
        )}
      </div>
    </div>
  )
}
