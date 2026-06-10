import type { InsightsResponse, RaceState, SessionSummary, Timeline } from './types'

const json = async <T>(path: string): Promise<T> => {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
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
