import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getCommentary, getFeed, getTimeline } from '../../api/client'
import type { Battle, CommentaryItem, FeedItem, Insight, RaceState, Timeline } from '../../api/types'
import { computeLiveGaps } from '../../lib/liveGaps'
import type { LiveGapResult, PositionsData } from '../../lib/liveGaps'
import { LANG_KEY, LEVEL_KEY, readLang, readLevel, tickMs } from './replayTypes'
import type { Lang, Level, Speed } from './replayTypes'
import type { ReplaySetters } from './replaySetters'
import { useGreenFlag } from './useGreenFlag'
import { useReplayStream } from './useReplayStream'
import { useSnapshotLoader } from './useSnapshotLoader'

/** Debounce before loading a snapshot while the user is scrubbing. */
const SCRUB_DEBOUNCE_MS = 150

export type { Lang, Level } from './replayTypes'

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
  /** Positions telemetry data (null if not available for this session). */
  positionsData: PositionsData | null
  /** Live gap estimates from telemetry; empty map if telemetry unavailable. */
  liveGaps: Map<string, LiveGapResult>
  /** True when the green flag strip should be shown. */
  greenFlag: boolean
  /** Text to display in the green flag strip. */
  greenFlagText: string
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
  const [positionsData, setPositionsData] = useState<PositionsData | null>(null)
  const [liveGaps, setLiveGaps] = useState<Map<string, LiveGapResult>>(new Map())

  const set = useMemo<ReplaySetters>(() => ({
    setState, setInsights, setBattles, setFeed, setCommentary,
    setAtMs, setLoading, setError, setFeedError, setPlaying,
  }), [])

  const { loadSnapshot } = useSnapshotLoader(sessionId, set)
  const { closeStream, openStream } = useReplayStream(sessionId, set)
  const { greenFlag, greenFlagText, reset: resetGreenFlag } = useGreenFlag(state)

  // Recompute live gaps whenever state or positions data changes
  useEffect(() => {
    if (!state || !positionsData) {
      setLiveGaps(new Map())
      return
    }
    setLiveGaps(computeLiveGaps(positionsData, state.at_ms, state.classification, state.drivers))
  }, [state, positionsData])

  // Session change: reset everything and load timeline + first snapshot
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
    setPositionsData(null)
    setLiveGaps(new Map())
    resetGreenFlag()

    if (!sessionId) return

    let cancelled = false

    // Fetch positions telemetry (non-critical, best-effort)
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}/positions`)
      .then((r) => r.ok ? r.json() as Promise<PositionsData> : null)
      .then((d) => { if (!cancelled) setPositionsData(d) })
      .catch(() => { if (!cancelled) setPositionsData(null) })

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
  }, [closeStream, loadSnapshot, resetGreenFlag, sessionId])

  // Re-fetch feed + commentary when lang/level change (without resetting position).
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
    if (playing) {
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
      }, SCRUB_DEBOUNCE_MS)
    },
    [closeStream, lang, level, loadSnapshot],
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
      if (playing) openStream(nextSpeed, atMs, lang, level)
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
    state, insights, battles, feed, commentary, timeline,
    playing, speed, frameMs, atMs, loading, error, feedError,
    lang, level, positionsData, liveGaps,
    greenFlag, greenFlagText,
    scrub, play, pause, setSpeed, setLang, setLevel,
  }
}
