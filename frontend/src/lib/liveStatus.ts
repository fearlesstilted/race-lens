import type { LiveStatusResult } from '../api/client'

export type LivePhase =
  | 'connecting'
  | 'waiting'
  | 'live'
  | 'reconnecting'
  | 'degraded'
  | 'stalled'
  | 'preparing'
  | 'failed'
  | 'ended'

export type LivePresentation = {
  phase: LivePhase
  badge: string
  detail: string
}

type LiveLifecycleOptions = {
  readonly: boolean
  explicitReplay: boolean
  attachedToLive: boolean
}

export type LiveLifecycle = {
  canManage: boolean
  remoteAvailable: boolean
  enterLive: boolean
  showLiveNow: boolean
  replaySessionId: string | null
}

export function restartCountdown(atMs: number, restartAtMs?: number | null): string | null {
  if (restartAtMs == null || restartAtMs <= atMs) return null
  const totalSec = Math.ceil((restartAtMs - atMs) / 1000)
  const mm = Math.floor(totalSec / 60).toString().padStart(2, '0')
  const ss = (totalSec % 60).toString().padStart(2, '0')
  return `${mm}:${ss}`
}

export function liveLifecycle(
  status: LiveStatusResult | null,
  options: LiveLifecycleOptions,
): LiveLifecycle {
  const remote = status?.source === 'remote'
  const remoteAttachable = remote && (
    status.status === 'live' || status.status === 'finishing'
  )
  const attachable = status?.is_running === true || remoteAttachable

  return {
    canManage: !options.readonly && !remote,
    remoteAvailable: remote && status.status === 'live',
    enterLive: !options.explicitReplay && !options.attachedToLive && attachable,
    showLiveNow: options.explicitReplay && !options.attachedToLive && remote && status.status === 'live',
    replaySessionId: !options.explicitReplay && options.attachedToLive
      && status?.status === 'replay_ready'
      ? status.replay_session_id ?? null
      : null,
  }
}

export function livePresentation(
  status: LiveStatusResult | null,
  hasState: boolean,
  streamError: string | null,
  now = Date.now(),
): LivePresentation {
  if (status?.status === 'idle') {
    return { phase: 'connecting', badge: 'LIVE OFF', detail: 'NO LIVE SESSION' }
  }
  if (status?.status === 'failed') {
    return {
      phase: 'failed',
      badge: 'LIVE FAILED',
      detail: status.failure ?? 'REPLAY PREPARATION FAILED',
    }
  }
  if (status?.status === 'finishing' || status?.status === 'replay_ready') {
    return {
      phase: 'preparing',
      badge: 'REPLAY PREPARING',
      detail: 'LIVE ENDED · PUBLISHING REPLAY',
    }
  }
  if (status?.capture_alive === false) {
    return { phase: 'stalled', badge: 'STALLED', detail: 'CAPTURE STOPPED · RESTART LIVE' }
  }
  const expiresAt = status?.expires_at ? Date.parse(status.expires_at) : Number.NaN
  if (!Number.isNaN(expiresAt) && expiresAt <= now) {
    return {
      phase: 'stalled',
      badge: 'STALLED',
      detail: 'SNAPSHOT STALE · BACKEND STALLED',
    }
  }
  if (status?.data_quality === 'stalled') {
    return { phase: 'stalled', badge: 'STALLED', detail: 'NO NEW DATA · BACKEND STALLED' }
  }
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
  if (status?.data_quality === 'degraded') {
    return { phase: 'degraded', badge: 'DELAYED', detail: 'LIVE DATA IS ARRIVING LATE' }
  }
  const generatedAt = status?.generated_at ? Date.parse(status.generated_at) : Number.NaN
  const snapshotAge = Number.isNaN(generatedAt) ? null : Math.max(0, Math.round((now - generatedAt) / 1000))
  return {
    phase: 'live',
    badge: '● LIVE',
    detail: status?.source === 'remote'
      ? `SNAPSHOT ${snapshotAge ?? '—'}S OLD · PLAY-FORWARD`
      : status ? `TIMING ACTIVE · POLL #${status.poll_count}` : 'TIMING ACTIVE',
  }
}
