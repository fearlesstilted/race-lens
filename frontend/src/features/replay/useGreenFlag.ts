/**
 * Green-flag strip logic. Shows on race start (first GREEN_FLAG_MS) or after a
 * neutralisation (red flag / SC / VSC) ends, derived purely from race state.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { RaceState } from '../../api/types'

/** How long the green-flag strip stays visible after race start or a restart. */
const GREEN_FLAG_MS = 15000

export type GreenFlag = {
  greenFlag: boolean
  greenFlagText: string
  reset: () => void
}

export function useGreenFlag(state: RaceState | null): GreenFlag {
  const [greenFlag, setGreenFlag] = useState(false)
  const [greenFlagText, setGreenFlagText] = useState('')
  const prevStatusRef = useRef<string | null>(null)
  const greenUntilRef = useRef<number>(0)

  useEffect(() => {
    if (!state) return
    const status = state.session_status ?? ''
    const atMs = state.at_ms
    const NEUTRAL = new Set(['red_flag', 'safety_car', 'vsc'])
    const prev = prevStatusRef.current

    if (prev !== null && NEUTRAL.has(prev) && status === 'started') {
      // Neutralisation ended → green flag
      greenUntilRef.current = atMs + GREEN_FLAG_MS
    } else if (atMs < GREEN_FLAG_MS && status === 'started' && greenUntilRef.current === 0) {
      // Race start (only set once)
      greenUntilRef.current = GREEN_FLAG_MS
    }

    prevStatusRef.current = status
    const isGreen = status === 'started' && atMs < greenUntilRef.current

    if (isGreen) {
      const text = atMs < GREEN_FLAG_MS && greenUntilRef.current <= GREEN_FLAG_MS
        ? 'RACE START — LIGHTS OUT'
        : 'GREEN FLAG — RACING RESUMED'
      setGreenFlagText(text)
    } else {
      setGreenFlagText('')
    }
    setGreenFlag(isGreen)
  }, [state])

  const reset = useCallback(() => {
    setGreenFlag(false)
    setGreenFlagText('')
    prevStatusRef.current = null
    greenUntilRef.current = 0
  }, [])

  return { greenFlag, greenFlagText, reset }
}
