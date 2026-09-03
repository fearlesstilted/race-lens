export const LIVE_TRACK_RETRY_MS = 3_000

export function isRetryableLiveTrackError(error: unknown): boolean {
  return error instanceof TypeError
    || (error instanceof Error && /^(?:404|502|503|504)(?:\s|:|$)/.test(error.message))
}

export function isRetryablePositionsError(error: unknown): boolean {
  return error instanceof TypeError
    || (error instanceof Error && /^(?:500|502|503|504)(?:\s|:|$)/.test(error.message))
}
