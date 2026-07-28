import { useMemo } from 'react'
import type { FeedItem, RaceMarker } from '../../api/types'

type Tone = 'race' | 'strategy' | 'incident' | 'radio'

type Candidate = {
  id: string
  atMs: number
  lap: number | null
  tone: Tone
  priority: number
  kicker: string
  title: string
}

const INCIDENTS = new Set([
  'RED_FLAG', 'SAFETY_CAR', 'VSC', 'CRASH', 'INCIDENT', 'OFF_TRACK', 'PENALTY',
])

type Props = {
  atMs: number
  playing: boolean
  speed: number
  lang: 'en' | 'ru'
  markers: RaceMarker[]
  feed: FeedItem[]
}

export function BroadcastOverlay({ atMs, playing, speed, lang, markers, feed }: Props) {
  const current = useMemo(() => {
    const candidates: Candidate[] = []
    for (const marker of markers) {
      let tone: Tone | null = null
      let priority = 0
      if (INCIDENTS.has(marker.kind)) {
        tone = 'incident'
        priority = 4
      } else if (marker.kind === 'LEAD_CHANGE' || marker.kind === 'OVERTAKE') {
        tone = 'race'
        priority = 3
      } else if (marker.kind === 'UNDERCUT') {
        tone = 'strategy'
        priority = 2
      }
      if (!tone) continue
      candidates.push({
        id: `marker:${marker.kind}:${marker.at_ms}:${marker.driver_ids.join(':')}`,
        atMs: marker.at_ms,
        lap: marker.lap,
        tone,
        priority,
        kicker: marker.kind.replaceAll('_', ' '),
        title: lang === 'ru' ? marker.text_ru : marker.text_en,
      })
    }
    for (const item of feed) {
      const radio = Boolean(item.audio_url) || item.text.startsWith('RADIO:')
      if (item.tag !== 'PIT' && !radio) continue
      candidates.push({
        id: item.id,
        atMs: item.at_ms,
        lap: item.lap,
        tone: radio ? 'radio' : 'strategy',
        priority: radio ? 1 : 2,
        kicker: radio
          ? `TEAM RADIO${item.transcript ? ' · MACHINE TRANSCRIPT' : ''}`
          : 'PIT STRATEGY',
        title: radio && item.transcript ? item.transcript : item.text,
      })
    }

    const windowMs = playing ? 8_000 * speed : 12_000
    return candidates
      .filter((item) => item.atMs <= atMs && atMs - item.atMs <= windowMs)
      .sort((a, b) => b.atMs - a.atMs || b.priority - a.priority)[0] ?? null
  }, [atMs, feed, lang, markers, playing, speed])

  if (!current) return null
  return (
    <aside
      key={current.id}
      className={`broadcast-overlay broadcast-overlay--${current.tone}`}
      role="status"
      aria-atomic="true"
    >
      <span className="broadcast-overlay__kicker">{current.kicker}</span>
      <strong>{current.title}</strong>
      <small>{current.lap ? `LAP ${current.lap}` : 'RACE UPDATE'} · REPLAY EVENT</small>
    </aside>
  )
}
