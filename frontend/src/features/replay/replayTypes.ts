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
export function writePersisted(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* noop */ }
}

/** Session statuses that count as a "neutralized" run (SC/VSC/red flag). */
export const NEUTRAL_STATUSES = new Set(['safety_car', 'vsc', 'red_flag'])
