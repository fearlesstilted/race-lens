const PRIMARY_REPLAY = 'hungarian_2026_race'
const FALLBACK_REPLAY = 'bahrain_2021_race'

export function recommendedReplay(sessionIds: readonly string[]): string | null {
  const ready = new Set(sessionIds)
  if (ready.has(PRIMARY_REPLAY)) return PRIMARY_REPLAY
  if (ready.has(FALLBACK_REPLAY)) return FALLBACK_REPLAY
  return sessionIds.find((id) => id.endsWith('_race')) ?? null
}
