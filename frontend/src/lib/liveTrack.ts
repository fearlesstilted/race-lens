export const LIVE_TRACK_RETRY_MS = 3_000

export function isLiveTrackNotFound(error: unknown): boolean {
  return error instanceof Error && /^404(?:\s|:|$)/.test(error.message)
}
