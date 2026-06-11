export type Speed = 1 | 5 | 10
export type Lang = 'en' | 'ru'
export type Level = 'beginner' | 'pro'

export const LANG_KEY = 'racelens_lang'
export const LEVEL_KEY = 'racelens_level'

export function readLang(): Lang {
  try { return (localStorage.getItem(LANG_KEY) as Lang) || 'en' } catch { return 'en' }
}
export function readLevel(): Level {
  try { return (localStorage.getItem(LEVEL_KEY) as Level) || 'pro' } catch { return 'pro' }
}

/** Adaptive wall-clock tick interval (ms) for the SSE stream by speed. */
export function tickMs(s: Speed): number {
  if (s === 1) return 500
  if (s === 5) return 1000
  return 2000
}
