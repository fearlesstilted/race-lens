export type PocketTarget = {
  version: 1
  mode: 'replay' | 'live'
  sessionId: string
  atMs: number | null
  focusedDrivers: string[]
}

const origin = 'https://race-lens.onrender.com'
const sessionIdPattern = /^[a-z0-9][a-z0-9_-]{0,79}$/
const driverIdPattern = /^[A-Z0-9]{2,5}$/

export function encodePocketLink(target: PocketTarget): string {
  const url = new URL('/pocket', origin)
  url.searchParams.set('v', String(target.version))
  url.searchParams.set('mode', target.mode)
  url.searchParams.set('session', target.sessionId)
  if (target.mode === 'replay') url.searchParams.set('at', String(Math.max(0, Math.round(target.atMs ?? 0))))
  if (target.focusedDrivers.length) url.searchParams.set('drivers', target.focusedDrivers.slice(0, 2).join(','))
  return url.toString()
}

export function encodePocketAppLink(target: PocketTarget): string {
  const url = new URL('racelens://pocket')
  url.search = new URL(encodePocketLink(target)).search
  return url.toString()
}

export function pocketBootstrap(target: PocketTarget | null) {
  const live = target?.mode === 'live'
  return { initialSessionId: live ? null : target?.sessionId ?? null, explicitReplay: Boolean(target) && !live, attachLive: live, replayPinned: Boolean(target) && !live }
}

export function parsePocketLink(url: URL): PocketTarget | null {
  if (url.origin !== origin || url.pathname !== '/pocket') return null
  const mode = url.searchParams.get('mode')
  const sessionId = url.searchParams.get('session')?.trim()
  const version = Number(url.searchParams.get('v'))
  const at = url.searchParams.get('at')
  const atMs = at === null ? null : Number(at)
  if (version !== 1 || !sessionId || !sessionIdPattern.test(sessionId) || (mode !== 'replay' && mode !== 'live')) return null
  if ((mode === 'live' && at !== null) || (mode === 'replay' && (atMs === null || !Number.isSafeInteger(atMs) || atMs < 0))) return null
  return {
    version: 1,
    mode,
    sessionId,
    atMs,
    focusedDrivers: (url.searchParams.get('drivers') ?? '').split(',').map((id) => id.trim()).filter((id) => driverIdPattern.test(id)).filter((id, i, ids) => ids.indexOf(id) === i).slice(0, 2),
  }
}
