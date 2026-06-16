export type SessionSummary = {
  session_id: string
}

export type Timeline = {
  session_id: string
  start_ms: number
  end_ms: number
  events_total: number
  lap_marks: Record<string, number>
}

export type DriverState = {
  position: number | null
  laps_completed: number
  last_lap_ms: number | null
  best_lap_ms: number | null
  gap_s: number | null
  interval_s: number | null
  tyre_compound: string | null
  tyre_age_laps: number | null
  pit_count: number
  in_pit: boolean
  retired: boolean
}

export type DataQuality = {
  status: string
  last_event_ms: number | null
  events_applied: number
  duplicates_dropped: number
}

export type Insight = {
  insight_id: string
  type: string
  severity: 'medium' | 'high' | string
  confidence: string
  created_at_ms: number
  lap: number
  driver_ids: string[]
  evidence: Record<string, number | string | boolean | null>
}

export type RaceState = {
  session_id: string | null
  at_ms: number
  lap: number
  session_status: string
  status_since_ms: number
  total_laps: number | null
  classification: string[]
  drivers: Record<string, DriverState>
  data_quality: DataQuality
  active_insights?: Insight[]
}

export type InsightsResponse = {
  at_ms: number
  insights: Insight[]
}

export type FeedItem = {
  at_ms: number
  lap: number | null
  text: string
  kind: string // 'status' | 'fastest_lap' | 'pit' | 'info' | ...
  tag?: 'PIT' | 'FLAG' | 'FASTEST' | 'INFO'
}

export type FeedResponse = {
  items: FeedItem[]
}

export type Battle = {
  leader_id: string
  chaser_id: string
  gap_s: number
}

export type BattlesResponse = {
  battles: Battle[]
}

export type CommentaryItem = {
  at_ms: number
  text: string
  driver_ids: string[]
  insight_id: string | null
  level: string
}

export type CommentaryResponse = {
  items: CommentaryItem[]
}

// ── Predictive / forecast types ───────────────────────────────────────────────

export type ForecastDriver = {
  projected_gap_s: number
  current_pos: number
  projected_pos: number
  delta_pos: number
}

export type Forecast = {
  at_ms: number
  laps_ahead: number
  projected_order: string[]
  projected: Record<string, ForecastDriver>
}

export type PitSimEvidence = {
  pit_loss_s: number
  rejoin_gap_s: number
  rejoin_pos: number
  key_rival: string | null
  margin_s: number | null
  verdict: 'UNDERCUT_LIKELY' | 'UNLIKELY' | 'NO_RIVAL'
}

export type PitSim = {
  driver: string
  confidence: string
  evidence: PitSimEvidence
  error?: string
}

export type Overtake = {
  ahead: string
  behind: string
  probability: number
  factors: Record<string, number | string | boolean>
  error?: string
}

// ── Win probability ───────────────────────────────────────────────────────────

export type WinProbEntry = { driver: string; prob: number }

export type WinProb = {
  at_ms: number
  laps_remaining: number
  win_prob: Record<string, number>
  leader: string | null
  top: WinProbEntry[]
}

export type WinProbSeriesPoint = {
  at_ms: number
  probs: Record<string, number>
}

// ── Race markers ──────────────────────────────────────────────────────────────

export type MarkerKind =
  | 'RED_FLAG'
  | 'SAFETY_CAR'
  | 'VSC'
  | 'GREEN'
  | 'INCIDENT'
  | 'CRASH'
  | 'PENALTY'
  | 'LEAD_CHANGE'
  | 'PODIUM_CHANGE'
  | 'FASTEST_LAP'

export type MarkerSeverity = 'critical' | 'high' | 'medium' | 'low'

export type RaceMarker = {
  at_ms: number
  lap: number
  kind: MarkerKind
  severity: MarkerSeverity
  driver_ids: string[]
  text_en: string
  text_ru: string
}

export type MarkersResponse = {
  markers: RaceMarker[]
}

// ── Highlights ────────────────────────────────────────────────────────────────

export type Highlight = {
  at_ms: number
  lap: number | null
  kind: MarkerKind
  title_en: string
  title_ru: string
  drivers: string[]
}

export type HighlightsResponse = {
  highlights: Highlight[]
}

// ── Driver of the Day ─────────────────────────────────────────────────────────

export type DotdCandidate = {
  driver: string
  score: number
  positions_gained: number
  had_fastest_lap: boolean
  note_en: string
  note_ru: string
}

export type DotdResponse = {
  candidates: DotdCandidate[]
  computed_pick: string | null
}

// ── What-If counterfactual ────────────────────────────────────────────────────

export type WhatIfDiff = {
  driver: string
  baseline_pos: number
  scenario_pos: number
  delta: number  // positive = gained positions
}

export type WhatIf = {
  scenario: string
  driver: string | null
  baseline_order: string[]
  scenario_order: string[]
  diff: WhatIfDiff[]
  summary_text_en: string
  summary_text_ru: string
  assumptions: string[]
}
