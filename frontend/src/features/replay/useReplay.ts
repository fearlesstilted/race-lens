import { useCallback, useEffect, useRef, useState } from 'react'
import { getBattles, getCommentary, getFeed, getInsights, getState, getTimeline, streamUrl } from '../../api/client'
import type { Battle, CommentaryItem, FeedItem, Insight, RaceState, Timeline } from '../../api/types'

type Speed = 1 | 5 | 10

export type ReplayModel = {
  state: RaceState | null
  insights: Insight[]
  battles: Battle[]
  feed: FeedItem[]
  commentary: CommentaryItem[]
  timeline: Timeline | null
  playing: boolean
  speed: Speed
  atMs: number
  loading: boolean
  error: string | null
  scrub: (atMs: number) => void
  play: () => void
  pause: () => void
  setSpeed: (speed: Speed) => void
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
  const sourceRef = useRef<EventSource | null>(null)
  const requestSeq = useRef(0)

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  const loadSnapshot = useCallback(
    async (nextAtMs: number) => {
      if (!sessionId) return
      const seq = ++requestSeq.current
      setLoading(true)
      setError(null)

      try {
        const [nextState, nextInsights, nextBattles, nextFeed, nextCommentary] = await Promise.all([
          getState(sessionId, nextAtMs),
          getInsights(sessionId, nextAtMs),
          getBattles(sessionId, nextAtMs).catch(() => ({ battles: [] })),
          getFeed(sessionId, nextAtMs, 30).catch(() => ({ items: [] })),
          getCommentary(sessionId, nextAtMs).catch(() => ({ items: [] })),
        ])
        if (seq !== requestSeq.current) return
        setState(nextState)
        setInsights(nextInsights.insights)
        setBattles(nextBattles.battles)
        setFeed(nextFeed.items)
        setCommentary(nextCommentary.items)
        setAtMs(nextState.at_ms)
      } catch (err) {
        if (seq !== requestSeq.current) return
        setError(err instanceof Error ? err.message : 'Could not load replay state')
      } finally {
        if (seq === requestSeq.current) setLoading(false)
      }
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

    if (!sessionId) return

    let cancelled = false
    setLoading(true)
    getTimeline(sessionId)
      .then((nextTimeline) => {
        if (cancelled) return undefined
        setTimeline(nextTimeline)
        setAtMs(nextTimeline.start_ms)
        return loadSnapshot(nextTimeline.start_ms)
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
  }, [closeStream, loadSnapshot, sessionId])

  const scrub = useCallback(
    (nextAtMs: number) => {
      closeStream()
      setPlaying(false)
      setAtMs(nextAtMs)
      window.setTimeout(() => {
        void loadSnapshot(nextAtMs)
      }, 150)
    },
    [closeStream, loadSnapshot],
  )

  const openStream = useCallback(
    (nextSpeed: Speed, startMs: number) => {
      if (!sessionId) return
      closeStream()
      setError(null)
      setPlaying(true)

      const source = new EventSource(streamUrl(sessionId, nextSpeed, startMs))
      sourceRef.current = source

      source.onmessage = (event) => {
        const nextState = JSON.parse(event.data) as RaceState
        setState(nextState)
        setInsights(nextState.active_insights ?? [])
        setAtMs(nextState.at_ms)
        // Refresh battles and feed from new at_ms
        const ms = nextState.at_ms
        void getBattles(sessionId, ms).then((r) => setBattles(r.battles)).catch(() => undefined)
        void getFeed(sessionId, ms, 30).then((r) => setFeed(r.items)).catch(() => undefined)
        void getCommentary(sessionId, ms).then((r) => setCommentary(r.items)).catch(() => undefined)
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
    openStream(speed, atMs)
  }, [atMs, openStream, sessionId, speed])

  const pause = useCallback(() => {
    closeStream()
    setPlaying(false)
  }, [closeStream])

  const setSpeed = useCallback(
    (nextSpeed: Speed) => {
      setSpeedValue(nextSpeed)
      if (playing) {
        openStream(nextSpeed, atMs)
      }
    },
    [atMs, openStream, playing],
  )

  return {
    state,
    insights,
    battles,
    feed,
    commentary,
    timeline,
    playing,
    speed,
    atMs,
    loading,
    error,
    scrub,
    play,
    pause,
    setSpeed,
  }
}
