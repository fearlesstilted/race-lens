import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FeedItem, Timeline } from '../../api/types'
import { formatRaceTime } from '../../lib/format'

type Speed = 1 | 5 | 10
const SPEEDS: Speed[] = [1, 5, 10]

type Props = {
  timeline: Timeline | null
  atMs: number
  playing: boolean
  speed: Speed
  /** Wall-clock ms between stream frames — for cursor transition. */
  frameMs: number
  feed: FeedItem[]
  onScrub: (ms: number) => void
  onPlay: () => void
  onPause: () => void
  onSpeed: (s: Speed) => void
}

type PhaseSegment = {
  kind: 'green' | 'red' | 'amber'
  pct: number
}

function buildPhase(feed: FeedItem[], startMs: number, endMs: number): PhaseSegment[] {
  if (endMs <= startMs) return [{ kind: 'green', pct: 100 }]

  const statusEvents: { ms: number; kind: 'green' | 'red' | 'amber' }[] = [
    { ms: startMs, kind: 'green' },
  ]

  for (const item of feed) {
    if (item.kind === 'red_flag' || item.kind === 'status' && item.text.toLowerCase().includes('red flag')) {
      statusEvents.push({ ms: item.at_ms, kind: 'red' })
    } else if (item.kind === 'safety_car' || item.text.toLowerCase().includes('safety car')) {
      statusEvents.push({ ms: item.at_ms, kind: 'amber' })
    } else if (item.kind === 'green_flag' || item.text.toLowerCase().includes('green flag') || item.text.toLowerCase().includes('race resumed')) {
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
      segments.push({ kind: seg.kind, pct: segPct })
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

export function ReplayDeck({ timeline, atMs, playing, speed, frameMs, feed, onScrub, onPlay, onPause, onSpeed }: Props) {
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

  const handleRailClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!railRef.current || !timeline) return
      const rect = railRef.current.getBoundingClientRect()
      const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1)
      onScrub(Math.round(startMs + ratio * duration))
    },
    [timeline, startMs, duration, onScrub],
  )

  const toggleSpoiler = useCallback(() => {
    setSpoilerFree((v) => {
      const next = !v
      try { localStorage.setItem(SPOILER_KEY, next ? '1' : '0') } catch { /* noop */ }
      return next
    })
  }, [])

  const sessionTime = formatRaceTime(atMs)
  const totalTime = formatRaceTime(endMs)

  const visiblePhases = useMemo(() => {
    if (!spoilerFree) return phases.map((seg, i) => ({ ...seg, key: i, neutral: false }))
    const result: { kind: string; pct: number; key: number; neutral: boolean }[] = []
    let accumulated = 0
    for (let i = 0; i < phases.length; i++) {
      const seg = phases[i]
      const segEnd = accumulated + seg.pct
      if (accumulated >= cursorPct) {
        result.push({ ...seg, key: i, neutral: true })
      } else if (segEnd > cursorPct) {
        const pastPct = cursorPct - accumulated
        const futurePct = segEnd - cursorPct
        result.push({ kind: seg.kind, pct: pastPct, key: i * 100, neutral: false })
        result.push({ kind: seg.kind, pct: futurePct, key: i * 100 + 1, neutral: true })
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
        {visiblePhases.map((seg) => (
          <i
            key={seg.key}
            className={seg.neutral ? 'ph-neutral' : `ph-${seg.kind === 'red' ? 'r' : seg.kind === 'amber' ? 's' : 'g'}`}
            style={{ width: `${seg.pct}%` }}
          />
        ))}
      </div>
      {/* Timeline rail */}
      <div className="rail" ref={railRef} onClick={handleRailClick}>
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
      </div>
      {/* Single control row: play/speeds left, spoiler+time right */}
      <div className="deckrow">
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
          {spoilerFree ? sessionTime : `${sessionTime} / ${totalTime}`}
        </span>
      </div>
    </div>
  )
}
