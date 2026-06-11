import React from 'react'
import type { FeedItem } from '../../api/types'

type Props = {
  items: FeedItem[]
}

function formatFeedTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function RaceFeed({ items }: Props) {
  return (
    <div className="ev-scroll">
      <div className="label">RACE FEED</div>
      {items.map((item, i) => {
        const isStatus = item.kind === 'status' || item.kind === 'red_flag' || item.kind === 'safety_car'
        const isFastest = item.kind === 'fastest_lap' || item.kind === 'LapCompleted'
        return (
          <div
            key={i}
            className={['ev', isStatus ? 'crit' : '', isFastest ? 'fast' : ''].filter(Boolean).join(' ')}
          >
            <span className="t">{formatFeedTime(item.at_ms)}</span>
            <span className="l">{item.lap !== null ? `L${item.lap}` : ''}</span>
            <span className="x">{item.text}</span>
          </div>
        )
      })}
      {items.length === 0 && (
        <div className="ev">
          <span className="t">—</span>
          <span className="l" />
          <span className="x">No events yet</span>
        </div>
      )}
    </div>
  )
}
