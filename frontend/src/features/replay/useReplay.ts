import { useCallback, useEffect, useRef, useState } from 'react'
import { getBattles, getCommentary, getFeed, getInsights, getState, getTimeline, streamUrl } from '../../api/client'
import type { Battle, CommentaryItem, FeedItem, Insight, RaceState, Timeline } from '../../api/types'

type Speed = 1 | 5 | 10
export type Lang = 'en' | 'ru'
export type Level = 'beginner' | 'pro'

const LANG_KEY = 'racelens_lang'
const LEVEL_KEY = 'racelens_level'

function readLang(): Lang {
  try { return (localStorage.getItem(LANG_KEY) as Lang) || 'en' } catch { return 'en' }
}
function readLevel(): Level {
  try { return (localStorage.getItem(LEVEL_KEY) as Level) || 'pro' } catch { return 'pro' }
}

export type ReplayModel = {
  state: RaceState | null
  insights: Insight[]
  battles: Battle[]
  feed: FeedItem[]
  commentary: CommentaryItem[]
  timeline: Timeline | null
  playing: boolean
  speed: Speed
  /** Wall-clock ms between stream frames (for CSS transitions). */
  frameMs: number
  atMs: number
  loading: boolean
  error: string | null
  feedError: string | null
  lang: Lang
  level: Level
  scrub: (atMs: number) => void
  play: () => void
  pause: () => void
  setSpeed: (speed: Speed) => void
  setLang: (lang: Lang) => void
  setLevel: (level: Level) => void
}

export const useReplay = (sessionId: string | null): ReplayModel => {
  const [state, setState] = useState<RaceState | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [battles, setBattles] = useState<Battle[]>([])
  const [feed, setFeed] = useState<FeedItem[]>([])
  const [commentary, setCommentary] = useState<CommentaryItem[]>([])
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeedValue] = useState<Speed>(10)
  const [atMs, setAtMs] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [feedError, setFeedError] = useState<string | null>(null)
  const [lang, setLangState] = useState<Lang>(readLang)
  const [level, setLevelState] = useState<Level>(readLevel)
  const sourceRef = useRef<EventSource | null>(null)
  const requestSeq = useRef(0)

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  const loadSnapshot = useCallback(
    async (nextAtMs: number, nextLang: Lang, nextLevel: Level) => {
      if (!sessionId) return
      const seq = ++requestSeq.current
      setLoading(true)
      setError(null)
      setFeedError(null)

      // Load state + insights in one batch; feed/battles/commentary separately (non-critical)
      let nextState: RaceState
      let nextInsights: { insights: Insight[] }
      try {
        ;[nextState, nextInsights] = await Promise.all([
          getState(sessionId, nextAtMs),
          getInsights(sessionId, nextAtMs),
        ])
      } catch (err) {
        if (seq !== requestSeq.current) return
        setError(err instanceof Error ? err.message : 'Could not load replay state')
        setLoading(false)
        return
      }

      if (seq !== requestSeq.current) return
      // Update atomically — never clear before new data arrives to avoid flicker
      setState(nextState)
      setInsights(nextInsights.insights)
      setAtMs(nextState.at_ms)

      // Feed + battles + commentary — errors shown in thin strip, not fatal
      const ms = nextState.at_ms
      const feedProm = getFeed(sessionId, ms, 30, nextLang)
        .then((r) => { if (seq === requestSeq.current) { setFeed(r.items); setFeedError(null) } })
        .catch((err: unknown) => {
          if (seq === requestSeq.current)
            setFeedError(err instanceof Error ? err.message : 'Feed unavailable')
        })
      const battlesProm = getBattles(sessionId, ms)
        .then((r) => { if (seq === requestSeq.current) setBattles(r.battles) })
        .catch(() => undefined)
      const commentaryProm = getCommentary(sessionId, ms, nextLang, nextLevel)
        .then((r) => { if (seq === requestSeq.current) setCommentary(r.items) })
        .catch(() => undefined)

      await Promise.allSettled([feedProm, battlesProm, commentaryProm])
      if (seq === requestSeq.current) setLoading(false)
    },
    [sessionId],
  )

  useEffect(() => {
    closeStream()
    setPlaying(false)
    setState(null)
    setInsights([])
    setBattles([])
    setFeed([])
    setCommentary([])
    setTimeline(null)
    setAtMs(0)
    setError(null)
    setFeedError(null)

    if (!sessionId) return

    let cancelled = false
    setLoading(true)
    getTimeline(sessionId)
      .then((nextTimeline) => {
        if (cancelled) return undefined
        setTimeline(nextTimeline)
        setAtMs(nextTimeline.start_ms)
        return loadSnapshot(nextTimeline.start_ms, lang, level)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Could not load replay timeline')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      closeStream()
    }
    // lang/level intentionally NOT in deps — session change resets; lang/level trigger own effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closeStream, loadSnapshot, sessionId])

  // Re-fetch feed + commentary when lang/level change (without resetting position).
  // If currently playing, also reopen the stream so commentary in SSE uses new lang/level.
  useEffect(() => {
    if (!sessionId || atMs === 0) return
    setFeedError(null)
    getFeed(sessionId, atMs, 30, lang)
      .then((r) => { setFeed(r.items); setFeedError(null) })
      .catch((err: unknown) => setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
    getCommentary(sessionId, atMs, lang, level)
      .then((r) => setCommentary(r.items))
      .catch(() => undefined)

    // Reopen stream with same position but new lang/level so live commentary updates
    if (sourceRef.current) {
      openStream(speed, atMs, lang, level)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, level])

  const scrub = useCallback(
    (nextAtMs: number) => {
      closeStream()
      setPlaying(false)
      setAtMs(nextAtMs)
      window.setTimeout(() => {
        void loadSnapshot(nextAtMs, lang, level)
      }, 150)
    },
    [closeStream, lang, level, loadSnapshot],
  )

  // Adaptive tick: keep wall-clock interval ~200-500ms for smooth playback
  const tickMs = useCallback((s: Speed): number => {
    if (s === 1) return 500
    if (s === 5) return 1000
    return 2000
  }, [])

  const openStream = useCallback(
    (nextSpeed: Speed, startMs: number, nextLang: Lang, nextLevel: Level) => {
      if (!sessionId) return
      closeStream()
      setError(null)
      setPlaying(true)

      const tick = tickMs(nextSpeed)
      const source = new EventSource(streamUrl(sessionId, nextSpeed, startMs, tick))
      sourceRef.current = source

      source.onmessage = (event) => {
        const nextState = JSON.parse(event.data) as RaceState
        setState(nextState)
        setInsights(nextState.active_insights ?? [])
        setAtMs(nextState.at_ms)
        const ms = nextState.at_ms
        void getBattles(sessionId, ms).then((r) => setBattles(r.battles)).catch(() => undefined)
        void getFeed(sessionId, ms, 30, nextLang)
          .then((r) => { setFeed(r.items); setFeedError(null) })
          .catch((err: unknown) => setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
        void getCommentary(sessionId, ms, nextLang, nextLevel)
          .then((r) => setCommentary(r.items)).catch(() => undefined)
      }

      source.addEventListener('end', () => {
        closeStream()
        setPlaying(false)
      })

      source.onerror = () => {
        closeStream()
        setPlaying(false)
        setError('Replay stream disconnected')
      }
    },
    [closeStream, sessionId],
  )

  const play = useCallback(() => {
    if (!sessionId) return
    openStream(speed, atMs, lang, level)
  }, [atMs, lang, level, openStream, sessionId, speed])

  const pause = useCallback(() => {
    closeStream()
    setPlaying(false)
  }, [closeStream])

  const setSpeed = useCallback(
    (nextSpeed: Speed) => {
      setSpeedValue(nextSpeed)
      if (playing) {
        openStream(nextSpeed, atMs, lang, level)
      }
    },
    [atMs, lang, level, openStream, playing],
  )

  const setLang = useCallback((nextLang: Lang) => {
    try { localStorage.setItem(LANG_KEY, nextLang) } catch { /* noop */ }
    setLangState(nextLang)
  }, [])

  const setLevel = useCallback((nextLevel: Level) => {
    try { localStorage.setItem(LEVEL_KEY, nextLevel) } catch { /* noop */ }
    setLevelState(nextLevel)
  }, [])

  // Wall-clock interval between frames: tick_ms(session) / speed
  const frameMs = tickMs(speed) / speed

  return {
    state,
    insights,
    battles,
    feed,
    commentary,
    timeline,
    playing,
    speed,
    frameMs,
    atMs,
    loading,
    error,
    feedError,
    lang,
    level,
    scrub,
    play,
    pause,
    setSpeed,
    setLang,
    setLevel,
  }
}
