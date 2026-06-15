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

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
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

      source.onmessage = (event) => {
        const raw = event.data as string
        // Live stream can send empty heartbeat `{}` while no data yet
        if (!raw || raw === '{}') return
        const nextState = JSON.parse(raw) as RaceState
        if (!nextState.at_ms) return
        set.setState(nextState)
        set.setInsights(nextState.active_insights ?? [])
        set.setAtMs(nextState.at_ms)
        const ms = nextState.at_ms
        if (sessionId) {
          void getBattles(sessionId, ms).then((r) => set.setBattles(r.battles)).catch(() => undefined)
          void getFeed(sessionId, ms, 30, nextLang)
            .then((r) => { set.setFeed(r.items); set.setFeedError(null) })
            .catch((err: unknown) => set.setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
          void getCommentary(sessionId, ms, nextLang, nextLevel)
            .then((r) => set.setCommentary(r.items)).catch(() => undefined)
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
