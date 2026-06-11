import React from 'react'
import type { FeedItem } from '../../api/types'

function fmtSessionTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const FeedRow = React.memo(function FeedRow({ item }: { item: FeedItem }) {
  const isStatus = item.kind === 'status' || item.kind === 'red_flag' || item.kind === 'safety_car'
  const isFastest = item.kind === 'fastest_lap' || item.kind === 'LapCompleted'
  return (
    <div
      className={['ev', isStatus ? 'crit' : '', isFastest ? 'fast' : ''].filter(Boolean).join(' ')}
    >
      {item.lap !== null ? (
        <span className="ev-lap">L{item.lap}</span>
      ) : (
        <span className="ev-lap" />
      )}
      <span className="t">{fmtSessionTime(item.at_ms)}</span>
      <span className="x">{item.text}</span>
    </div>
  )
})

export function RaceFeed({ items }: { items: FeedItem[] }) {
  return (
    <div className="ev-scroll">
      <div className="label">RACE FEED</div>
      {items.map((item) => (
        <FeedRow key={`${item.at_ms}|${item.kind}|${item.text.slice(0, 20)}`} item={item} />
      ))}
      {items.length === 0 && (
        <div className="ev">
          <span className="ev-lap" />
          <span className="t">—</span>
          <span className="x">No events yet</span>
        </div>
      )}
    </div>
  )
}
