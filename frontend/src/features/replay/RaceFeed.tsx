import React, { useEffect, useRef, useState } from 'react'
import type { FeedItem } from '../../api/types'

function fmtSessionTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

type Tag = 'PIT' | 'FLAG' | 'FASTEST' | 'FINISH' | 'PASS' | 'INFO'

const TAG_LABELS: Record<Tag, string> = {
  FLAG: 'FLAG',
  PIT: 'PIT',
  FASTEST: 'FAST',
  FINISH: 'FIN',
  PASS: 'PASS',
  INFO: 'INFO',
}

// One shared <audio> element: only ever one team-radio clip plays at a time.
const radioAudio = typeof Audio !== 'undefined' ? new Audio() : null

const FeedRow = React.memo(function FeedRow({
  item,
  flash,
  playingUrl,
  onToggleRadio,
}: {
  item: FeedItem
  flash: boolean
  playingUrl: string | null
  onToggleRadio: (url: string) => void
}) {
  const isStatus = item.kind === 'status' || item.kind === 'red_flag' || item.kind === 'safety_car'
  const isFastest = item.kind === 'fastest_lap' || item.kind === 'LapCompleted'
  const tag = (item.tag ?? 'INFO') as Tag
  const isPlaying = !!item.audio_url && item.audio_url === playingUrl
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
        {item.audio_url && (
          <button
            type="button"
            className={`ev-radio-btn${isPlaying ? ' playing' : ''}`}
            onClick={() => onToggleRadio(item.audio_url!)}
            aria-label={isPlaying ? 'Stop team radio' : 'Play team radio'}
            title={isPlaying ? 'Stop team radio' : 'Play team radio'}
          >
            {isPlaying ? '■' : '▶'}
          </button>
        )}
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
  const [playingUrl, setPlayingUrl] = useState<string | null>(null)

  // Stop-and-clear when the clip finishes on its own.
  useEffect(() => {
    if (!radioAudio) return
    const onEnded = () => setPlayingUrl(null)
    radioAudio.addEventListener('ended', onEnded)
    return () => radioAudio.removeEventListener('ended', onEnded)
  }, [])

  const handleToggleRadio = (url: string) => {
    if (!radioAudio) return
    if (playingUrl === url) {
      radioAudio.pause()
      setPlayingUrl(null)
      return
    }
    radioAudio.src = url
    void radioAudio.play()
    setPlayingUrl(url)
  }

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
          <FeedRow
            key={k}
            item={item}
            flash={flashKeys.has(k)}
            playingUrl={playingUrl}
            onToggleRadio={handleToggleRadio}
          />
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
