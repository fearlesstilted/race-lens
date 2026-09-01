import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from './url.ts'

export type CompanionState = {
  race_id: string
  mode: 'replay' | 'live'
  at_ms: number | null
  selected_driver_ids: string[]
}

export type CompanionSnapshot = {
  link_id: string
  revision: number
  expires_at: string
  state: CompanionState
}

export type CompanionStatus = 'disconnected' | 'linked' | 'reconnecting' | 'expired'
export type CompanionAction = Partial<CompanionState>
export type CompanionCredentials = { linkId: string; secret: string }
export type CompanionLinkModel = {
  status: CompanionStatus
  shareUrl: string | null
  busy: boolean
  createError: string | null
  create: () => Promise<void>
  leave: () => void
  publish: (action: CompanionAction) => void
}

type PendingAction = { action: CompanionAction; retried: boolean }

export type CompanionSync = {
  status: CompanionStatus
  revision: number | null
  expires_at: string | null
  state: CompanionState | null
  pending: PendingAction | null
}

type CompanionEvent =
  | { type: 'remote'; snapshot: CompanionSnapshot }
  | { type: 'local'; state: CompanionState | null; action: CompanionAction }
  | { type: 'conflict'; snapshot: CompanionSnapshot }
  | { type: 'patched'; snapshot: CompanionSnapshot }
  | { type: 'network-error' }
  | { type: 'expired' }
  | { type: 'leave' }

export type CompanionEffect =
  | { type: 'apply'; state: CompanionState }
  | { type: 'patch'; expected_revision: number; state: CompanionState }

export function initialCompanionSync(): CompanionSync {
  return { status: 'disconnected', revision: null, expires_at: null, state: null, pending: null }
}

export function parseCompanionInvite(url: URL): (CompanionCredentials & { cleanPath: string }) | null {
  const match = url.pathname.match(/^\/companion\/([^/]+)\/?$/)
  const secret = new URLSearchParams(url.hash.slice(1)).get('token')
  if (!match || !secret) return null
  try {
    const linkId = decodeURIComponent(match[1])
    return { linkId, secret, cleanPath: `/companion/${encodeURIComponent(linkId)}` }
  } catch {
    return null
  }
}

export function shareCompanionUrl({ linkId, secret }: CompanionCredentials): string {
  return `https://race-lens.onrender.com/companion/${encodeURIComponent(linkId)}#token=${encodeURIComponent(secret)}`
}

export function applyCompanionAction(
  current: CompanionState,
  action: CompanionAction,
): CompanionState {
  const next = { ...current, ...action }
  const selected = [...new Set(next.selected_driver_ids.map((id) => id.trim()).filter(Boolean))].slice(0, 2)
  return {
    race_id: next.race_id.trim() || current.race_id,
    mode: next.mode,
    at_ms: next.mode === 'live'
      ? null
      : Math.max(0, Math.round(Number.isFinite(next.at_ms) ? next.at_ms! : current.at_ms ?? 0)),
    selected_driver_ids: selected,
  }
}

export function resolvePendingLiveNavigation(
  pending: boolean,
  directSessionId: string | null,
  canonicalSessionId: string | null,
): { pending: boolean; action: CompanionAction | null } {
  const raceId = directSessionId || canonicalSessionId
  if (!pending || !raceId) return { pending, action: null }
  return {
    pending: false,
    action: { mode: 'live', race_id: raceId, at_ms: null, selected_driver_ids: [] },
  }
}

export function transitionCompanion(
  sync: CompanionSync,
  event: CompanionEvent,
): { sync: CompanionSync; effects: CompanionEffect[] } {
  if (event.type === 'leave') return { sync: initialCompanionSync(), effects: [] }
  if (event.type === 'expired') {
    return { sync: { ...sync, status: 'expired', pending: null }, effects: [] }
  }
  if (event.type === 'network-error') {
    return { sync: { ...sync, status: 'reconnecting' }, effects: [] }
  }
  if ((event.type === 'remote' || event.type === 'patched') && sync.revision !== null) {
    if (event.snapshot.revision === sync.revision) {
      return {
        sync: {
          ...sync,
          status: 'linked',
          expires_at: event.snapshot.expires_at,
          pending: event.type === 'patched' ? null : sync.pending,
        },
        effects: [],
      }
    }
    if (event.snapshot.revision < sync.revision) return { sync, effects: [] }
  }
  if (event.type === 'conflict' && sync.revision !== null && event.snapshot.revision < sync.revision) {
    if (event.type === 'conflict' && sync.pending && !sync.pending.retried && sync.state) {
      const state = applyCompanionAction(sync.state, sync.pending.action)
      return {
        sync: { ...sync, pending: { ...sync.pending, retried: true } },
        effects: [
          { type: 'apply', state },
          { type: 'patch', expected_revision: sync.revision, state },
        ],
      }
    }
    return { sync, effects: [] }
  }
  if (event.type === 'remote') {
    if (sync.revision === null && sync.pending) {
      const state = applyCompanionAction(event.snapshot.state, sync.pending.action)
      return {
        sync: {
          status: 'linked',
          revision: event.snapshot.revision,
          expires_at: event.snapshot.expires_at,
          state: event.snapshot.state,
          pending: { ...sync.pending, retried: true },
        },
        effects: [
          { type: 'apply', state: event.snapshot.state },
          { type: 'apply', state },
          { type: 'patch', expected_revision: event.snapshot.revision, state },
        ],
      }
    }
    return {
      sync: {
        status: 'linked',
        revision: event.snapshot.revision,
        expires_at: event.snapshot.expires_at,
        state: event.snapshot.state,
        pending: null,
      },
      effects: [{ type: 'apply', state: event.snapshot.state }],
    }
  }
  if (event.type === 'patched') {
    return {
      sync: {
        status: 'linked',
        revision: event.snapshot.revision,
        expires_at: event.snapshot.expires_at,
        state: event.snapshot.state,
        pending: null,
      },
      effects: [],
    }
  }
  if (event.type === 'local') {
    if (sync.revision === null) {
      return { sync: { ...sync, pending: { action: event.action, retried: false } }, effects: [] }
    }
    if (!event.state) return { sync, effects: [] }
    const state = applyCompanionAction(event.state, event.action)
    return {
      sync: { ...sync, pending: { action: event.action, retried: false } },
      effects: [{ type: 'patch', expected_revision: sync.revision, state }],
    }
  }

  const current = {
    status: 'linked' as const,
    revision: event.snapshot.revision,
    expires_at: event.snapshot.expires_at,
    state: event.snapshot.state,
    pending: sync.pending,
  }
  if (!sync.pending || sync.pending.retried) {
    return {
      sync: { ...current, status: 'reconnecting', pending: null },
      effects: [{ type: 'apply', state: event.snapshot.state }],
    }
  }
  const state = applyCompanionAction(event.snapshot.state, sync.pending.action)
  return {
    sync: { ...current, pending: { ...sync.pending, retried: true } },
    effects: [
      { type: 'apply', state: event.snapshot.state },
      { type: 'apply', state },
      { type: 'patch', expected_revision: event.snapshot.revision, state },
    ],
  }
}

class CompanionRequestError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Companion Link request failed (${status})`)
    this.status = status
  }
}

const STORAGE_KEY = 'race_lens_companion_link'

function writeCredentials(credentials: CompanionCredentials | null) {
  try {
    if (credentials) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(credentials))
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch { /* session-only fallback */ }
}

function initialCredentials(): CompanionCredentials | null {
  const invite = parseCompanionInvite(new URL(window.location.href))
  if (invite) {
    const credentials = { linkId: invite.linkId, secret: invite.secret }
    writeCredentials(credentials)
    window.history.replaceState(null, '', `${invite.cleanPath}${window.location.search}`)
    return credentials
  }
  try {
    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<CompanionCredentials> | null
    return typeof stored?.linkId === 'string' && typeof stored.secret === 'string'
      ? { linkId: stored.linkId, secret: stored.secret }
      : null
  } catch {
    return null
  }
}

async function companionFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(apiUrl(path), init)
  if (!response.ok) throw new CompanionRequestError(response.status)
  return response.json() as Promise<T>
}

function authHeaders(credentials: CompanionCredentials): HeadersInit {
  return {
    Authorization: `Bearer ${credentials.secret}`,
    'Content-Type': 'application/json',
  }
}

function getCompanion(
  credentials: CompanionCredentials,
  afterRevision: number,
  waitSeconds: number,
  signal?: AbortSignal,
) {
  return companionFetch<CompanionSnapshot>(
    `/api/companion-links/${encodeURIComponent(credentials.linkId)}`
      + `?after_revision=${afterRevision}&wait_seconds=${waitSeconds}`,
    { headers: authHeaders(credentials), signal },
  )
}

function patchCompanion(
  credentials: CompanionCredentials,
  expectedRevision: number,
  state: CompanionState,
) {
  return companionFetch<CompanionSnapshot>(
    `/api/companion-links/${encodeURIComponent(credentials.linkId)}`,
    {
      method: 'PATCH',
      headers: authHeaders(credentials),
      body: JSON.stringify({ expected_revision: expectedRevision, state }),
    },
  )
}

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export function useCompanionLink(
  currentState: CompanionState | null,
  onRemoteState: (state: CompanionState, previous: CompanionState | null) => void,
): CompanionLinkModel {
  const [credentials, setCredentials] = useState<CompanionCredentials | null>(initialCredentials)
  const [sync, setSync] = useState<CompanionSync>(() => ({
    ...initialCompanionSync(),
    status: credentials ? 'reconnecting' as const : 'disconnected' as const,
  }))
  const [busy, setBusy] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const credentialsRef = useRef(credentials)
  const currentStateRef = useRef(currentState)
  const onRemoteRef = useRef(onRemoteState)
  const appliedStateRef = useRef<CompanionState | null>(null)
  const syncRef = useRef(sync)
  const publishQueue = useRef(Promise.resolve())

  useEffect(() => { credentialsRef.current = credentials }, [credentials])
  useEffect(() => { currentStateRef.current = currentState }, [currentState])
  useEffect(() => { onRemoteRef.current = onRemoteState }, [onRemoteState])

  const commit = useCallback((next: CompanionSync) => {
    syncRef.current = next
    setSync(next)
  }, [])

  const applyEffects = useCallback((effects: CompanionEffect[]) => {
    for (const effect of effects) {
      if (effect.type === 'apply') {
        const previous = appliedStateRef.current
        appliedStateRef.current = effect.state
        onRemoteRef.current(effect.state, previous)
      }
    }
  }, [])

  const disconnect = useCallback((expired: boolean) => {
    const result = transitionCompanion(syncRef.current, { type: expired ? 'expired' : 'leave' })
    commit(result.sync)
    if (!expired) {
      appliedStateRef.current = null
      credentialsRef.current = null
      setCredentials(null)
      writeCredentials(null)
      setCreateError(null)
    }
  }, [commit])

  const handleRequestError = useCallback((error: unknown) => {
    if (error instanceof CompanionRequestError && error.status === 410) {
      disconnect(true)
    } else if (error instanceof CompanionRequestError && [401, 404].includes(error.status)) {
      disconnect(false)
    } else {
      commit(transitionCompanion(syncRef.current, { type: 'network-error' }).sync)
    }
  }, [commit, disconnect])

  const sendPatch = useCallback(async (
    activeCredentials: CompanionCredentials,
    initial: ReturnType<typeof transitionCompanion>,
  ) => {
    if (credentialsRef.current !== activeCredentials) return
    let result = initial
    let patch = result.effects.find((effect) => effect.type === 'patch')
    if (!patch) return
    try {
      const snapshot = await patchCompanion(activeCredentials, patch.expected_revision, patch.state)
      if (credentialsRef.current !== activeCredentials) return
      const patched = transitionCompanion(syncRef.current, { type: 'patched', snapshot })
      if (patched.sync.revision === snapshot.revision) appliedStateRef.current = snapshot.state
      commit(patched.sync)
    } catch (error) {
      if (credentialsRef.current !== activeCredentials) return
      if (!(error instanceof CompanionRequestError) || error.status !== 409) {
        handleRequestError(error)
        return
      }
      try {
        const latest = await getCompanion(activeCredentials, result.sync.revision ?? -1, 0)
        if (credentialsRef.current !== activeCredentials) return
        result = transitionCompanion(
          { ...syncRef.current, pending: result.sync.pending },
          { type: 'conflict', snapshot: latest },
        )
        commit(result.sync)
        applyEffects(result.effects)
        patch = result.effects.find((effect) => effect.type === 'patch')
        if (!patch) return
        try {
          const snapshot = await patchCompanion(activeCredentials, patch.expected_revision, patch.state)
          if (credentialsRef.current !== activeCredentials) return
          const patched = transitionCompanion(syncRef.current, { type: 'patched', snapshot })
          if (patched.sync.revision === snapshot.revision) appliedStateRef.current = snapshot.state
          commit(patched.sync)
        } catch (retryError) {
          if (credentialsRef.current !== activeCredentials) return
          if (!(retryError instanceof CompanionRequestError) || retryError.status !== 409) {
            handleRequestError(retryError)
            return
          }
          const current = await getCompanion(activeCredentials, result.sync.revision ?? -1, 0)
          if (credentialsRef.current !== activeCredentials) return
          const stopped = transitionCompanion(
            { ...syncRef.current, pending: result.sync.pending },
            { type: 'conflict', snapshot: current },
          )
          commit(stopped.sync)
          applyEffects(stopped.effects)
        }
      } catch (latestError) {
        if (credentialsRef.current !== activeCredentials) return
        handleRequestError(latestError)
      }
    }
  }, [applyEffects, commit, handleRequestError])

  useEffect(() => {
    if (!credentials) return
    let cancelled = false
    let first = syncRef.current.revision === null
    let failures = 0
    const controller = new AbortController()

    const poll = async () => {
      while (!cancelled) {
        const before = syncRef.current.revision
        try {
          const snapshot = await getCompanion(
            credentials,
            before ?? 0,
            first ? 0 : 25,
            controller.signal,
          )
          if (cancelled || credentialsRef.current !== credentials) return
          const result = transitionCompanion(
            syncRef.current,
            { type: 'remote', snapshot },
          )
          first = false
          failures = 0
          commit(result.sync)
          applyEffects(result.effects)
          if (result.effects.some((effect) => effect.type === 'patch')) {
            publishQueue.current = publishQueue.current.then(() => sendPatch(credentials, result))
          }
        } catch (error) {
          if (cancelled || controller.signal.aborted || credentialsRef.current !== credentials) return
          handleRequestError(error)
          if (error instanceof CompanionRequestError && [401, 404, 410].includes(error.status)) return
          await delay(Math.min(5000, 500 * (2 ** failures++)))
        }
      }
    }

    void poll()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [applyEffects, commit, credentials, handleRequestError, sendPatch])

  const create = useCallback(async () => {
    const state = currentStateRef.current
    if (!state || busy) return
    setBusy(true)
    setCreateError(null)
    try {
      const created = await companionFetch<CompanionSnapshot & { secret: string }>('/api/companion-links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state }),
      })
      const nextCredentials = { linkId: created.link_id, secret: created.secret }
      credentialsRef.current = nextCredentials
      setCredentials(nextCredentials)
      writeCredentials(nextCredentials)
      appliedStateRef.current = created.state
      commit(transitionCompanion(initialCompanionSync(), { type: 'patched', snapshot: created }).sync)
    } catch {
      setCreateError('Could not create link. Try again.')
    } finally {
      setBusy(false)
    }
  }, [busy, commit])

  const leave = useCallback(() => {
    disconnect(false)
    if (/^\/companion\//.test(window.location.pathname)) {
      window.history.replaceState(null, '', `/${window.location.search}`)
    }
  }, [disconnect])

  const publish = useCallback((action: CompanionAction) => {
    const activeCredentials = credentialsRef.current
    if (!activeCredentials) return
    publishQueue.current = publishQueue.current.then(async () => {
      if (credentialsRef.current !== activeCredentials) return
      const state = syncRef.current.state ?? currentStateRef.current
      if (syncRef.current.status === 'expired') return

      const result = transitionCompanion(syncRef.current, { type: 'local', state, action })
      commit(result.sync)
      await sendPatch(activeCredentials, result)
    })
  }, [commit, sendPatch])

  return {
    status: sync.status,
    shareUrl: credentials ? shareCompanionUrl(credentials) : null,
    busy,
    createError,
    create,
    leave,
    publish,
  }
}
