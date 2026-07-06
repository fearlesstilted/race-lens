/**
 * EventSource (SSE) playback stream. Owns the connection lifecycle and pushes
 * each streamed frame into shared state via the setters bundle.
 *
 * The caller supplies a `getStreamUrl` factory so replay and live can share
 * this hook without duplicating SSE logic.
 */
import { useCallback, useRef } from 'react'
import { getBattles, getCommentary, getFeed, getLiveFeed } from '../../api/client'
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
  // Throttle ONLY the network side-data (feed / battles / commentary) so we don't
  // flood the API at high speed. The table + scrubber + map are NOT throttled —
  // they must render the same frame, else the tower lags the track by up to
  // DATA_THROTTLE_MS * speed of session time (the map/table desync bug).
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

      // Network side-data (feed / battles / commentary). Throttled — these are
      // API round-trips, not the on-screen frame. The table/map are NOT here.
      const flushSideData = (st: RaceState) => {
        lastDataRef.current = performance.now()
        const ms = st.at_ms
        if (sessionId) {
          void getBattles(sessionId, ms).then((r) => set.setBattles(r.battles)).catch(() => undefined)
          void getFeed(sessionId, ms, 30, nextLang)
            .then((r) => { set.setFeed(r.items); set.setFeedError(null) })
            .catch((err: unknown) => set.setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
          void getCommentary(sessionId, ms, nextLang, nextLevel)
            .then((r) => set.setCommentary(r.items)).catch(() => undefined)
        } else {
          // Live mode has no session_id to scope by — feed comes from the live
          // engine's own event log. Battles/commentary stay replay-only.
          void getLiveFeed(30, nextLang)
            .then((r) => { set.setFeed(r.items); set.setFeedError(null) })
            .catch((err: unknown) => set.setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
        }
      }

      source.onmessage = (event) => {
        const raw = event.data as string
        // Live stream can send empty heartbeat `{}` while no data yet
        if (!raw || raw === '{}') return
        const nextState = JSON.parse(raw) as RaceState
        // at_ms can legitimately be 0 (live joins anchor early events at t=0).
        if (nextState.at_ms == null) return
        // Table, scrubber and map all read the SAME frame — push every frame so
        // the tower can never lag the track. rank is stable (Step 1), so the
        // FLIP tower no longer strobes when updated per frame.
        set.setAtMs(nextState.at_ms)
        set.setState(nextState)
        set.setInsights(nextState.active_insights ?? [])
        // Only the network side-data is throttled (leading + trailing).
        pendingRef.current = nextState
        const elapsed = performance.now() - lastDataRef.current
        if (elapsed >= DATA_THROTTLE_MS) {
          if (trailRef.current) { clearTimeout(trailRef.current); trailRef.current = null }
          flushSideData(nextState)
        } else if (!trailRef.current) {
          trailRef.current = setTimeout(() => {
            trailRef.current = null
            if (pendingRef.current) flushSideData(pendingRef.current)
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
