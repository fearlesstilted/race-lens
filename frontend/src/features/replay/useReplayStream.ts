/**
 * EventSource (SSE) playback stream. Owns the connection lifecycle and pushes
 * each streamed frame into shared state via the setters bundle.
 *
 * The caller supplies a `getStreamUrl` factory so replay and live can share
 * this hook without duplicating SSE logic.
 */
import { useCallback, useRef } from 'react'
import { getBattles, getCommentary, getFeed } from '../../api/client'
import type { RaceState } from '../../api/types'
import type { Lang, Level, Speed } from './replayTypes'
import type { ReplaySetters } from './replaySetters'

export type StreamUrlFactory = (speed: Speed, atMs: number, lang: Lang, level: Level) => string

export function useReplayStream(
  /** null = no active session, stream stays closed */
  active: boolean,
  /** Factory returns the SSE URL; called each time we (re-)open. */
  getStreamUrl: StreamUrlFactory,
  /** Used for side-data (feed/battles/commentary) — null in live mode with no sessionId. */
  sessionId: string | null,
  set: ReplaySetters,
) {
  const sourceRef = useRef<EventSource | null>(null)
  // Throttle the data-heavy, animated updates (table / insights / feed) so they
  // don't strobe at high playback speed (the stream can push ~5 frames/sec).
  const lastDataRef = useRef(0)
  const pendingRef = useRef<RaceState | null>(null)
  const trailRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const DATA_THROTTLE_MS = 600

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
    if (trailRef.current) {
      clearTimeout(trailRef.current)
      trailRef.current = null
    }
  }, [])

  const openStream = useCallback(
    (nextSpeed: Speed, startMs: number, nextLang: Lang, nextLevel: Level) => {
      if (!active) return
      closeStream()
      set.setError(null)
      set.setPlaying(true)

      const url = getStreamUrl(nextSpeed, startMs, nextLang, nextLevel)
      const source = new EventSource(url)
      sourceRef.current = source

      // Push the data-heavy, animated state (table / insights / feed / battles /
      // commentary). Rate-limited via the throttle below.
      const flushData = (st: RaceState) => {
        lastDataRef.current = performance.now()
        set.setState(st)
        set.setInsights(st.active_insights ?? [])
        const ms = st.at_ms
        if (sessionId) {
          void getBattles(sessionId, ms).then((r) => set.setBattles(r.battles)).catch(() => undefined)
          void getFeed(sessionId, ms, 30, nextLang)
            .then((r) => { set.setFeed(r.items); set.setFeedError(null) })
            .catch((err: unknown) => set.setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
          void getCommentary(sessionId, ms, nextLang, nextLevel)
            .then((r) => set.setCommentary(r.items)).catch(() => undefined)
        }
      }

      source.onmessage = (event) => {
        const raw = event.data as string
        // Live stream can send empty heartbeat `{}` while no data yet
        if (!raw || raw === '{}') return
        const nextState = JSON.parse(raw) as RaceState
        if (!nextState.at_ms) return
        // Clock / scrubber / map stay smooth — atMs is cheap, push every frame.
        set.setAtMs(nextState.at_ms)
        // Table / insights / feed are throttled (leading + trailing) so they
        // settle calmly instead of strobing on every frame.
        pendingRef.current = nextState
        const elapsed = performance.now() - lastDataRef.current
        if (elapsed >= DATA_THROTTLE_MS) {
          if (trailRef.current) { clearTimeout(trailRef.current); trailRef.current = null }
          flushData(nextState)
        } else if (!trailRef.current) {
          trailRef.current = setTimeout(() => {
            trailRef.current = null
            if (pendingRef.current) flushData(pendingRef.current)
          }, DATA_THROTTLE_MS - elapsed)
        }
      }

      source.addEventListener('end', () => {
        closeStream()
        set.setPlaying(false)
      })

      source.onerror = () => {
        closeStream()
        set.setPlaying(false)
        set.setError('Stream disconnected')
      }
    },
    [active, closeStream, getStreamUrl, sessionId, set],
  )

  return { sourceRef, closeStream, openStream }
}
