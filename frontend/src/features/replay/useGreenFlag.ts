/**
 * Green-flag flash logic.
 *
 * Shows a short banner (~4 s session-time) ONLY:
 *   - at race start (atMs < 4000 ms)
 *   - when a GREEN marker from the markers list falls within 4 s before current atMs
 *
 * This is deterministic at any scrub position (no wall-clock timers), uses the
 * pre-loaded markers array from useReplay.
 */
import { useMemo } from 'react'
import type { RaceMarker } from '../../api/types'

const GREEN_FLASH_MS = 4000
// Cars line up on the grid this long before lights-out (matches main.tsx rows gate).
const GRID_FORM_MS = 10000

export type GreenFlag = {
  greenFlag: boolean
  greenFlagText: string
  /** no-op kept for API compatibility with useReplay reset on session change */
  reset: () => void
}

export function useGreenFlag(
  atMs: number,
  markers: RaceMarker[],
): GreenFlag {
  const result = useMemo(() => {
    // Pre-start, negative session time (telemetry before lights-out):
    //   running the formation lap → ON the grid (last GRID_FORM_MS) → lights out.
    if (atMs < -GRID_FORM_MS) {
      return { greenFlag: true, greenFlagText: 'FORMATION LAP' }
    }
    if (atMs < 0) {
      return { greenFlag: true, greenFlagText: 'ON THE GRID' }
    }

    // Race start flash (lights out at t=0)
    if (atMs >= 0 && atMs < GREEN_FLASH_MS) {
      return { greenFlag: true, greenFlagText: 'LIGHTS OUT' }
    }

    // Find the most recent GREEN marker within the flash window
    const recent = markers
      .filter((m) => m.kind === 'GREEN' && m.at_ms <= atMs && atMs - m.at_ms < GREEN_FLASH_MS)
      .sort((a, b) => b.at_ms - a.at_ms)[0]

    if (recent) {
      return { greenFlag: true, greenFlagText: 'GREEN FLAG · RACING RESUMED' }
    }

    return { greenFlag: false, greenFlagText: '' }
  }, [atMs, markers])

  return { ...result, reset: () => undefined }
}
