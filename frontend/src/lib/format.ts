export const formatRaceTime = (ms: number) => {
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

// "monaco_2024_race" → "Monaco 2024 — Race"
// Splits on underscore, Title Cases each part, joins with space,
// then replaces the last word with " — LastWord" to mark the session type.
export const sessionLabel = (sessionId: string): string => {
  const parts = sessionId.split('_').map((p) => p.charAt(0).toUpperCase() + p.slice(1))
  if (parts.length < 2) return parts.join(' ')
  const sessionType = parts.pop()!
  return `${parts.join(' ')} — ${sessionType}`
}
