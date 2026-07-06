// 2026 grid — official TeamColour values straight from the F1 live-timing
// DriverList feed (recorded Silverstone 2026). Unknown drivers fall back to
// grey, which reads as a ghost car — update this map when the grid changes.
export const TEAM_COLORS: Record<string, string> = {
  // Ferrari
  LEC: '#ED1131', HAM: '#ED1131',
  // Mercedes
  RUS: '#00D7B6', ANT: '#00D7B6',
  // Red Bull Racing
  VER: '#4781D7', HAD: '#4781D7',
  // McLaren
  NOR: '#F47600', PIA: '#F47600',
  // Racing Bulls
  LIN: '#6C98FF', LAW: '#6C98FF',
  // Audi
  BOR: '#F50537', HUL: '#F50537',
  // Haas
  BEA: '#9C9FA2', OCO: '#9C9FA2',
  // Williams
  SAI: '#1868DB', ALB: '#1868DB',
  // Alpine
  GAS: '#00A1E8', COL: '#00A1E8',
  // Cadillac
  BOT: '#909090', PER: '#909090',
  // Aston Martin
  ALO: '#229971', STR: '#229971',
}

export const teamColor = (driverCode: string): string =>
  TEAM_COLORS[driverCode.toUpperCase()] ?? '#555555'

// ── Tyre compound colors ───────────────────────────────────────────────────
// Canonical (broadcast-style) palette — single source of truth for all
// compound-coloured UI (stint bars, on-track compound rings, etc).

export const COMPOUND_COLORS = {
  SOFT: '#e8002d',
  MEDIUM: '#f2c500',
  HARD: '#e8e8ec',
  INTERMEDIATE: '#3cba54',
  WET: '#2d6fe8',
  UNKNOWN: '#5a5a63',
} as const

export type CompoundKey = keyof typeof COMPOUND_COLORS

const COMPOUND_ALIASES: Record<string, CompoundKey> = {
  S: 'SOFT',
  SOFT: 'SOFT',
  M: 'MEDIUM',
  MEDIUM: 'MEDIUM',
  H: 'HARD',
  HARD: 'HARD',
  I: 'INTERMEDIATE',
  INTER: 'INTERMEDIATE',
  INTERMEDIATE: 'INTERMEDIATE',
  W: 'WET',
  WET: 'WET',
}

/** Normalize a compound value ('SOFT' / 'S' / 'soft' / …) to a canonical key, or null if unrecognized/absent. */
export function normalizeCompound(input: string | null | undefined): CompoundKey | null {
  if (!input) return null
  return COMPOUND_ALIASES[input.trim().toUpperCase()] ?? null
}

/** Resolve a compound value to its canonical color. Unrecognized/absent input falls back to UNKNOWN gray. */
export const compoundColor = (input: string | null | undefined): string =>
  COMPOUND_COLORS[normalizeCompound(input) ?? 'UNKNOWN']
