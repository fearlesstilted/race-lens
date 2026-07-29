import type { LiveStatusResult } from '../api/client'

export type LivePhase =
  | 'connecting'
  | 'waiting'
  | 'live'
  | 'reconnecting'
  | 'degraded'
  | 'stalled'
  | 'ended'

export type LivePresentation = {
  phase: LivePhase
  badge: string
  detail: string
}

export function livePresentation(
  status: LiveStatusResult | null,
  hasState: boolean,
  streamError: string | null,
): LivePresentation {
  if (streamError) {
    return {
      phase: 'reconnecting',
      badge: 'RECONNECTING',
      detail: 'STREAM LOST · RETRYING AUTOMATICALLY',
    }
  }
  if (status && !status.is_running) {
    return { phase: 'ended', badge: 'ENDED', detail: 'SESSION FEED ENDED' }
  }
  if (status?.capture_alive === false) {
    return { phase: 'stalled', badge: 'STALLED', detail: 'CAPTURE STOPPED · RESTART LIVE' }
  }
  if (!hasState) {
    if (status?.is_running && status.events_total === 0) {
      return {
        phase: 'waiting',
        badge: 'WAITING',
        detail: 'FEED CONNECTED · WAITING FOR FIRST TIMING PACKET',
      }
    }
    return { phase: 'connecting', badge: 'CONNECTING', detail: 'OPENING LIVE TIMING' }
  }
  if (status?.data_quality === 'stalled') {
    return { phase: 'stalled', badge: 'STALLED', detail: 'NO NEW DATA · CHECK CAPTURE' }
  }
  if (status?.data_quality === 'degraded') {
    return { phase: 'degraded', badge: 'DELAYED', detail: 'LIVE DATA IS ARRIVING LATE' }
  }
  return {
    phase: 'live',
    badge: '● LIVE',
    detail: status ? `TIMING ACTIVE · POLL #${status.poll_count}` : 'TIMING ACTIVE',
  }
}
