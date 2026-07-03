/**
 * Shared fetch-in-effect hook. Same request-sequence guard pattern as
 * useSnapshotLoader: an older resolve can never overwrite a newer one.
 *
 * Resets to {data: null, loading: false, error: null} whenever `deps`
 * change (regardless of `enabled`), then — if `enabled` — runs `fn` and
 * populates loading/data/error. Cleans up (ignores in-flight results) on
 * unmount or before the next run.
 */
import { useEffect, useRef, useState } from 'react'

export type AsyncState<T> = {
  data: T | null
  loading: boolean
  error: string | null
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], enabled = true): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: false, error: null })
  const seq = useRef(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  // Reset whenever `deps` change, regardless of `enabled` — keeps stale data
  // from a previous key (e.g. sessionId) from lingering once re-enabled.
  useEffect(() => {
    seq.current++
    setState({ data: null, loading: false, error: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    if (!enabled) return
    const mySeq = ++seq.current
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    fnRef.current()
      .then((data) => {
        if (cancelled || mySeq !== seq.current) return
        setState({ data, loading: false, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled || mySeq !== seq.current) return
        setState({ data: null, loading: false, error: err instanceof Error ? err.message : String(err) })
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled])

  return state
}
