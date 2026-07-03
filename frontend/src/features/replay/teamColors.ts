export const TEAM_COLORS: Record<string, string> = {
  LEC: '#e10600',
  SAI: '#e10600',
  PIA: '#ff8700',
  NOR: '#ff8700',
  RUS: '#00d2be',
  HAM: '#00d2be',
  VER: '#0600ef',
  PER: '#0600ef',
  TSU: '#2b4562',
  RIC: '#2b4562',
  ALO: '#006f62',
  STR: '#006f62',
  GAS: '#0090ff',
  OCO: '#0090ff',
  ALB: '#005aff',
  SAR: '#005aff',
  BOT: '#900000',
  ZHO: '#900000',
  MAG: '#ffffff',
  HUL: '#ffffff',
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
