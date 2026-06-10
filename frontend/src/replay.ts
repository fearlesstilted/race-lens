export type RaceEvent = {
  event_id: string
  session_id: string
  type: string
  session_time_ms: number
  lap?: number
  driver_id?: string
  source?: string
  confidence?: string
  payload?: Record<string, unknown>
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

export type RaceState = {
  session_id: string | null
  at_ms: number
  lap: number
  session_status: string
  total_laps: number | null
  classification: string[]
  drivers: Record<string, DriverState>
  data_quality: {
    status: string
    last_event_ms: number | null
    events_applied: number
    duplicates_dropped: number
  }
}

const newDriver = (): DriverState => ({
  position: null,
  laps_completed: 0,
  last_lap_ms: null,
  best_lap_ms: null,
  gap_s: null,
  interval_s: null,
  tyre_compound: null,
  tyre_age_laps: null,
  pit_count: 0,
  in_pit: false,
})

const numberPayload = (event: RaceEvent, key: string): number | null => {
  const value = event.payload?.[key]
  return typeof value === 'number' ? value : null
}

const stringPayload = (event: RaceEvent, key: string): string | null => {
  const value = event.payload?.[key]
  return typeof value === 'string' ? value : null
}

const driver = (state: RaceState, driverId: string): DriverState => {
  state.drivers[driverId] ??= newDriver()
  return state.drivers[driverId]
}

export const parseJsonl = (text: string): RaceEvent[] =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as RaceEvent)
    .sort((a, b) =>
      a.session_time_ms === b.session_time_ms
        ? a.event_id.localeCompare(b.event_id)
        : a.session_time_ms - b.session_time_ms,
    )

export const stateAt = (events: RaceEvent[], atMs: number): RaceState => {
  const state: RaceState = {
    session_id: events[0]?.session_id ?? null,
    at_ms: atMs,
    lap: 0,
    session_status: 'unknown',
    total_laps: null,
    classification: [],
    drivers: {},
    data_quality: {
      status: 'unknown',
      last_event_ms: null,
      events_applied: 0,
      duplicates_dropped: 0,
    },
  }

  const seen = new Set<string>()
  let lastEventMs: number | null = null

  for (const event of events) {
    if (event.session_time_ms > atMs) break
    if (seen.has(event.event_id)) {
      state.data_quality.duplicates_dropped += 1
      continue
    }
    seen.add(event.event_id)
    applyEvent(state, event)
    state.data_quality.events_applied += 1
    lastEventMs = event.session_time_ms
  }

  state.data_quality.last_event_ms = lastEventMs
  state.data_quality.status =
    lastEventMs === null ? 'unknown' : atMs - lastEventMs > 120_000 ? 'stale' : 'good'

  state.classification = Object.entries(state.drivers)
    .filter(([, value]) => value.position !== null)
    .sort(([, a], [, b]) => (a.position ?? 999) - (b.position ?? 999))
    .map(([driverId]) => driverId)

  return state
}

const applyEvent = (state: RaceState, event: RaceEvent) => {
  const driverId = event.driver_id

  if (event.type === 'SessionStarted') {
    state.session_status = 'started'
    state.total_laps = numberPayload(event, 'total_laps')
    return
  }

  if (event.type === 'SessionStatusChanged') {
    state.session_status = stringPayload(event, 'status') ?? state.session_status
    return
  }

  if (!driverId) return

  if (event.type === 'LapCompleted') {
    const d = driver(state, driverId)
    d.laps_completed = Math.max(d.laps_completed, event.lap ?? 0)
    const lapMs = numberPayload(event, 'lap_time_ms')
    if (lapMs !== null) {
      d.last_lap_ms = lapMs
      d.best_lap_ms = d.best_lap_ms === null ? lapMs : Math.min(d.best_lap_ms, lapMs)
    }
    if (d.tyre_age_laps !== null) d.tyre_age_laps += 1
    state.lap = Math.max(state.lap, event.lap ?? 0)
  } else if (event.type === 'PositionChanged') {
    driver(state, driverId).position = numberPayload(event, 'position')
  } else if (event.type === 'GapUpdated') {
    driver(state, driverId).gap_s = numberPayload(event, 'gap_s')
  } else if (event.type === 'IntervalUpdated') {
    driver(state, driverId).interval_s = numberPayload(event, 'interval_s')
  } else if (event.type === 'PitIn') {
    const d = driver(state, driverId)
    d.in_pit = true
    d.pit_count += 1
  } else if (event.type === 'PitOut') {
    driver(state, driverId).in_pit = false
  } else if (event.type === 'TyreStintUpdated') {
    const d = driver(state, driverId)
    d.tyre_compound = stringPayload(event, 'compound')
    d.tyre_age_laps = numberPayload(event, 'age_laps') ?? 0
  }
}

export const formatRaceTime = (ms: number) => {
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export const formatLapTime = (ms: number | null) => {
  if (ms === null) return '—'
  const minutes = Math.floor(ms / 60_000)
  const seconds = ((ms % 60_000) / 1000).toFixed(3).padStart(6, '0')
  return `${minutes}:${seconds}`
}
