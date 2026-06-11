import React, { useEffect, useRef, useState } from 'react'
import type { FeedItem } from '../../api/types'

function fmtSessionTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

type Tag = 'PIT' | 'FLAG' | 'FASTEST' | 'INFO'

const TAG_LABELS: Record<Tag, string> = {
  FLAG: 'FLAG',
  PIT: 'PIT',
  FASTEST: 'FAST',
  INFO: 'INFO',
}

const FeedRow = React.memo(function FeedRow({ item, flash }: { item: FeedItem; flash: boolean }) {
  const isStatus = item.kind === 'status' || item.kind === 'red_flag' || item.kind === 'safety_car'
  const isFastest = item.kind === 'fastest_lap' || item.kind === 'LapCompleted'
  const tag = (item.tag ?? 'INFO') as Tag
  return (
    <div
      className={[
        'ev',
        isStatus ? 'crit' : '',
        isFastest ? 'fast' : '',
        flash ? 'ev-flash' : '',
      ].filter(Boolean).join(' ')}
    >
      {item.lap !== null ? (
        <span className="ev-lap">L{item.lap}</span>
      ) : (
        <span className="ev-lap" />
      )}
      <span className="t">{fmtSessionTime(item.at_ms)}</span>
      <span className="x">
        <span className={`ev-tag ev-tag-${tag.toLowerCase()}`}>{TAG_LABELS[tag]}</span>
        {item.text}
      </span>
    </div>
  )
})

function itemKey(item: FeedItem): string {
  return `${item.at_ms}|${item.kind}|${item.text.slice(0, 20)}`
}

export function RaceFeed({ items, compact }: { items: FeedItem[]; compact?: boolean }) {
  const prevKeysRef = useRef<Set<string>>(new Set())
  const [flashKeys, setFlashKeys] = useState<Set<string>>(new Set())

  useEffect(() => {
    const newKeys = new Set<string>()
    for (const item of items) {
      const k = itemKey(item)
      if (!prevKeysRef.current.has(k)) {
        newKeys.add(k)
      }
    }
    prevKeysRef.current = new Set(items.map(itemKey))
    if (newKeys.size > 0) {
      setFlashKeys(newKeys)
      const t = window.setTimeout(() => setFlashKeys(new Set()), 2000)
      return () => clearTimeout(t)
    }
  }, [items])

  return (
    <div className={compact ? 'ev-scroll ev-scroll-compact' : 'ev-scroll'}>
      {!compact && <div className="label">RACE FEED</div>}
      {items.map((item) => {
        const k = itemKey(item)
        return (
          <FeedRow key={k} item={item} flash={flashKeys.has(k)} />
        )
      })}
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
