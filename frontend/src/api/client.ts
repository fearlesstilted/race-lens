import type { BattlesResponse, CommentaryResponse, DotdResponse, FeedItem, FeedResponse, Forecast, HighlightsResponse, InsightsResponse, MarkersResponse, Overtake, PitSim, RaceState, SessionSummary, Timeline, WhatIf, WinProb, WinProbSeriesPoint } from './types'

const json = async <T>(path: string): Promise<T> => {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${path}`)
  }
  return (await response.json()) as T
}

export const listSessions = () => json<SessionSummary[]>('/api/sessions')

export const getTimeline = (sessionId: string) =>
  json<Timeline>(`/api/sessions/${encodeURIComponent(sessionId)}/timeline`)

export const getState = (sessionId: string, atMs: number) =>
  json<RaceState>(`/api/sessions/${encodeURIComponent(sessionId)}/state?at_ms=${atMs}`)

export const getInsights = (sessionId: string, atMs: number) =>
  json<InsightsResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/insights?at_ms=${atMs}`)

export const streamUrl = (sessionId: string, speed: number, fromMs: number, tickMs = 1000) =>
  `/api/sessions/${encodeURIComponent(sessionId)}/stream?speed=${speed}&from_ms=${fromMs}&tick_ms=${tickMs}`

/** The backend returns a bare list; normalise to {items} for the rest of the app. */
export const getFeed = async (sessionId: string, untilMs: number, limit = 30, lang = 'en'): Promise<FeedResponse> => {
  const raw = await json<FeedItem[] | FeedResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/feed?until_ms=${untilMs}&lang=${lang}&limit=${limit}`,
  )
  if (Array.isArray(raw)) return { items: raw }
  return raw
}

export const getBattles = (sessionId: string, atMs: number) =>
  json<BattlesResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/battles?at_ms=${atMs}`)

export const getCommentary = (sessionId: string, atMs: number, lang = 'en', level = 'pro') =>
  json<CommentaryResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/commentary?at_ms=${atMs}&lang=${lang}&level=${level}`)

export type TrackCorner = { number: number; x: number; y: number }
export type TrackData = { session_id: string; viewbox: [number, number]; points: [number, number][]; corners?: TrackCorner[] }

export const getTrack = (sessionId: string) =>
  json<TrackData>(`/api/sessions/${encodeURIComponent(sessionId)}/track`)

// ── Predictive endpoints (replay only; live forecast not implemented) ─────────
//
// NOTE: These endpoints are session-scoped (/sessions/{id}/…) and only
// available in replay mode.  In live mode (DataSource kind='live') the
// PROJECTION toggle is hidden so these are never called.

export const getForecast = (sessionId: string, atMs: number, laps = 10) =>
  json<Forecast>(
    `/api/sessions/${encodeURIComponent(sessionId)}/forecast?at_ms=${atMs}&laps=${laps}`,
  )

export const getSimulatePit = (sessionId: string, atMs: number, driver: string) =>
  json<PitSim>(
    `/api/sessions/${encodeURIComponent(sessionId)}/simulate-pit?at_ms=${atMs}&driver=${encodeURIComponent(driver)}`,
  )

export const getOvertake = (sessionId: string, atMs: number, ahead: string, behind: string) =>
  json<Overtake>(
    `/api/sessions/${encodeURIComponent(sessionId)}/overtake?at_ms=${atMs}&ahead=${encodeURIComponent(ahead)}&behind=${encodeURIComponent(behind)}`,
  )

export const getWinProb = (sessionId: string, atMs: number) =>
  json<WinProb>(
    `/api/sessions/${encodeURIComponent(sessionId)}/win-prob?at_ms=${atMs}`,
  )

export const getWinProbSeries = (sessionId: string, untilMs: number, samples = 20) =>
  json<WinProbSeriesPoint[]>(
    `/api/sessions/${encodeURIComponent(sessionId)}/win-prob-series?until_ms=${untilMs}&samples=${samples}`,
  )

export const getWhatIf = (sessionId: string, atMs: number, scenario: string, driver?: string) => {
  const params = new URLSearchParams({ at_ms: String(atMs), scenario })
  if (driver) params.set('driver', driver)
  return json<WhatIf>(`/api/sessions/${encodeURIComponent(sessionId)}/what-if?${params.toString()}`)
}

export const getMarkers = (sessionId: string, untilMs?: number) =>
  json<MarkersResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/markers${untilMs !== undefined ? `?until_ms=${untilMs}` : ''}`,
  )

export const getHighlights = (sessionId: string, topN = 8) =>
  json<HighlightsResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/highlights?top_n=${topN}`,
  )

export const getDriverOfDay = (sessionId: string) =>
  json<DotdResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/driver-of-day`)

// ── Live endpoints ────────────────────────────────────────────────────────────

export type LiveStartResult = { session_key: number; poll_interval_s: number; status: string }
export type LiveStatusResult = {
  is_running: boolean
  poll_count: number
  last_poll_ok: boolean | null
  last_poll_at: string | null
  error_count: number
  data_quality: string // 'good' | 'degraded' | 'stalled'
}

const post = async <T>(path: string): Promise<T> => {
  const response = await fetch(path, { method: 'POST' })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${path}`)
  return (await response.json()) as T
}

export const liveStart = (year: number, country: string, session: string, pollS = 2) =>
  post<LiveStartResult>(
    `/api/live/start?year=${year}&country=${encodeURIComponent(country)}&session=${encodeURIComponent(session)}&poll_s=${pollS}`,
  )

export const liveStatus = () => json<LiveStatusResult>('/api/live/status')

export const liveStop = () => post<LiveStatusResult>('/api/live/stop')

export const liveStreamUrl = (lang: string, level: string, tickS = 2) =>
  `/api/live/stream?tick_s=${tickS}&lang=${lang}&level=${level}`

export const getLiveState = () => json<import('./types').RaceState>('/api/live/state')

// ── Live lobby ────────────────────────────────────────────────────────────────

export interface LiveSessionInfo {
  session_name: string
  session_key: number
  session_type: string
  date_start: string
  started: boolean
}

export const getLiveSessions = (year: number, country?: string): Promise<LiveSessionInfo[]> => {
  const params = new URLSearchParams({ year: String(year) })
  if (country) params.set('country', country)
  return json<LiveSessionInfo[]>(`/api/live/sessions?${params.toString()}`)
}
