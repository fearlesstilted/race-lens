import type { BattlesResponse, CommentaryResponse, FeedItem, FeedResponse, InsightsResponse, RaceState, SessionSummary, Timeline } from './types'

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
