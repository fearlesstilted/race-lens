import { useEffect, useRef } from 'react'
import type { FeedItem } from '../../api/types'

// Feed tags worth interrupting the user's ears for: flags, fastest laps,
// on-track passes. PIT/INFO/radio stay silent.
const SPOKEN_TAGS = new Set(['FASTEST', 'FLAG', 'PASS'])

// More new items than this in one tick = backlog swap (mount, session switch,
// scrub), not live news — absorb silently instead of reading 30 lines aloud.
const MAX_SPOKEN_PER_TICK = 5

/** Speak newly-arrived feed items via the built-in speechSynthesis. */
export function useVoiceAlerts(
  items: FeedItem[],
  enabled: boolean,
  lang: string,
  contextKey: string | null,
) {
  const seenRef = useRef<Set<string> | null>(null)

  useEffect(() => {
    seenRef.current = null
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    return () => window.speechSynthesis.cancel()
  }, [contextKey])

  useEffect(() => {
    if (!enabled && typeof window !== 'undefined' && 'speechSynthesis' in window)
      window.speechSynthesis.cancel()
  }, [enabled])

  useEffect(() => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    const keys = items.map((i) => i.id)
    if (seenRef.current === null) {
      seenRef.current = new Set(keys) // initial backlog stays silent
      return
    }
    const seen = seenRef.current
    const fresh = items.filter((_, idx) => !seen.has(keys[idx]))
    keys.forEach((k) => seen.add(k))
    if (!enabled || fresh.length === 0 || fresh.length > MAX_SPOKEN_PER_TICK) return
    for (const item of fresh) {
      if (!SPOKEN_TAGS.has(item.tag ?? '')) continue
      const u = new SpeechSynthesisUtterance(item.text)
      u.lang = lang === 'ru' ? 'ru-RU' : 'en-GB'
      window.speechSynthesis.speak(u)
    }
  }, [items, enabled, lang])
}
