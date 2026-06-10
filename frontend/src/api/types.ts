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
