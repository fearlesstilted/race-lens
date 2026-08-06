export type Speed = 1 | 5 | 10
export type Lang = 'en' | 'ru'
export type Level = 'beginner' | 'pro'
export type ReviewDock = 'anchor' | 'left' | 'right'
export type DashboardLayout = {
  center: 'battles' | 'track'
  timing: boolean
  insights: boolean
  feed: boolean
}

export const LANG_KEY = 'racelens_lang'
export const LEVEL_KEY = 'racelens_level'
const DASHBOARD_KEY = 'racelens_dashboard_layout'
const REVIEW_DOCK_KEY = 'racelens_review_dock'

export const DASHBOARD_PRESETS: Record<'race' | 'battles' | 'clean', DashboardLayout> = {
  race: { center: 'battles', timing: true, insights: true, feed: true },
  battles: { center: 'battles', timing: false, insights: true, feed: true },
  clean: { center: 'battles', timing: true, insights: false, feed: false },
}

export function readLang(): Lang {
  try { return (localStorage.getItem(LANG_KEY) as Lang) || 'en' } catch { return 'en' }
}
export function readLevel(): Level {
  try { return (localStorage.getItem(LEVEL_KEY) as Level) || 'pro' } catch { return 'pro' }
}
export function readDashboardLayout(): DashboardLayout {
  try {
    const stored = JSON.parse(localStorage.getItem(DASHBOARD_KEY) ?? '')
    return {
      center: stored.center === 'track' ? 'track' : 'battles',
      timing: stored.timing !== false,
      insights: stored.insights !== false,
      feed: stored.feed !== false,
    }
  } catch {
    return { ...DASHBOARD_PRESETS.race }
  }
}
export function writeDashboardLayout(layout: DashboardLayout) {
  writePersisted(DASHBOARD_KEY, JSON.stringify(layout))
}

export function parseReviewDock(value: string | null): ReviewDock {
  return value === 'left' || value === 'right' ? value : 'anchor'
}

export function readReviewDock(): ReviewDock {
  try { return parseReviewDock(localStorage.getItem(REVIEW_DOCK_KEY)) } catch { return 'anchor' }
}

export function writeReviewDock(value: ReviewDock) {
  writePersisted(REVIEW_DOCK_KEY, value)
}

export function writePersisted(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* noop */ }
}

/** Session statuses that count as a "neutralized" run (SC/VSC/red flag). */
export const NEUTRAL_STATUSES = new Set(['safety_car', 'vsc', 'red_flag'])
