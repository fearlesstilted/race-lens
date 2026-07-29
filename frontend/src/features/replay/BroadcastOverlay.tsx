import { useMemo } from 'react'
import type { FeedItem, RaceMarker } from '../../api/types'
import { selectBroadcastCandidate } from '../../lib/broadcastOverlay'

type Props = {
  atMs: number
  playing: boolean
  speed: number
  lang: 'en' | 'ru'
  markers: RaceMarker[]
  feed: FeedItem[]
}

export function BroadcastOverlay({ atMs, playing, speed, lang, markers, feed }: Props) {
  const current = useMemo(
    () => selectBroadcastCandidate({ atMs, playing, speed, lang, markers, feed }),
    [atMs, feed, lang, markers, playing, speed],
  )

  if (!current) return null
  return (
    <aside
      key={current.id}
      className={`broadcast-overlay broadcast-overlay--${current.tone}`}
      role="status"
      aria-atomic="true"
    >
      <span className="broadcast-overlay__kicker">
        <i aria-hidden="true" />
        {current.kicker}
      </span>
      <div className="broadcast-overlay__body">
        <strong>{current.title}</strong>
        <small>{current.lap ? `LAP ${current.lap}` : 'RACE UPDATE'} · REPLAY EVENT</small>
      </div>
    </aside>
  )
}
