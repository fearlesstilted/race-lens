/**
 * EventSource (SSE) playback stream. Owns the connection lifecycle and pushes
 * each streamed frame into shared state via the setters bundle.
 */
import { useCallback, useRef } from 'react'
import { getBattles, getCommentary, getFeed, streamUrl } from '../../api/client'
import type { RaceState } from '../../api/types'
import { tickMs } from './replayTypes'
import type { Lang, Level, Speed } from './replayTypes'
import type { ReplaySetters } from './replaySetters'

export function useReplayStream(sessionId: string | null, set: ReplaySetters) {
  const sourceRef = useRef<EventSource | null>(null)

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  const openStream = useCallback(
    (nextSpeed: Speed, startMs: number, nextLang: Lang, nextLevel: Level) => {
      if (!sessionId) return
      closeStream()
      set.setError(null)
      set.setPlaying(true)

      const tick = tickMs(nextSpeed)
      const source = new EventSource(streamUrl(sessionId, nextSpeed, startMs, tick))
      sourceRef.current = source

      source.onmessage = (event) => {
        const nextState = JSON.parse(event.data) as RaceState
        set.setState(nextState)
        set.setInsights(nextState.active_insights ?? [])
        set.setAtMs(nextState.at_ms)
        const ms = nextState.at_ms
        void getBattles(sessionId, ms).then((r) => set.setBattles(r.battles)).catch(() => undefined)
        void getFeed(sessionId, ms, 30, nextLang)
          .then((r) => { set.setFeed(r.items); set.setFeedError(null) })
          .catch((err: unknown) => set.setFeedError(err instanceof Error ? err.message : 'Feed unavailable'))
        void getCommentary(sessionId, ms, nextLang, nextLevel)
          .then((r) => set.setCommentary(r.items)).catch(() => undefined)
      }

      source.addEventListener('end', () => {
        closeStream()
        set.setPlaying(false)
      })

      source.onerror = () => {
        closeStream()
        set.setPlaying(false)
        set.setError('Replay stream disconnected')
      }
    },
    [closeStream, sessionId, set],
  )

  return { sourceRef, closeStream, openStream }
}
