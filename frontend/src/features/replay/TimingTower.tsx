import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Battle, DriverState } from '../../api/types'
import type { LiveGapResult } from '../../lib/liveGaps'
import { teamColor } from './teamColors'

type DriverRow = { id: string } & DriverState

type Props = {
  rows: DriverRow[]
  battles: Battle[]
  selectedIds: string[]
  onSelectDriver: (id: string) => void
  /** Live gap estimates from telemetry; key = driver_id */
  liveGaps?: Map<string, LiveGapResult>
}

function fmtLastLap(ms: number | null): string {
  if (ms === null || ms <= 0) return '—'
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const t = Math.floor((ms % 1000) / 100)
  return `${m}:${String(s).padStart(2, '0')}.${t}`
}

/** Pace trend: compare last_lap_ms vs mean of recent_laps_ms (fallback: best_lap_ms). */
function paceTrend(row: DriverRow): 'up' | 'down' | null {
  const last = row.last_lap_ms
  if (!last || last <= 0) return null

  // recent_laps_ms is not in the type yet; access via cast
  const recent = (row as Record<string, unknown>)['recent_laps_ms']
  let avg: number | null = null

  if (Array.isArray(recent) && recent.length > 0) {
    const valid = (recent as number[]).filter((v) => v > 0)
    if (valid.length > 0) avg = valid.reduce((a, b) => a + b, 0) / valid.length
  }

  if (avg === null) return null

  const delta = last - avg
  if (delta < -300) return 'up'   // faster (lower is better)
  if (delta > 300) return 'down'
  return null
}

export const TimingTower = React.memo(function TimingTower({
  rows,
  battles,
  selectedIds,
  onSelectDriver,
  liveGaps,
}: Props) {
  const battleSet = useMemo(() => {
    const s = new Set<string>()
    for (const b of battles) {
      s.add(b.leader_id)
      s.add(b.chaser_id)
    }
    return s
  }, [battles])

  const rowCount = rows.length || 1

  // ── Fastest lap across peloton ────────────────────────────────
  const fastestLapHolder = useMemo(() => {
    let best: number | null = null
    let bestId: string | null = null
    for (const row of rows) {
      if (row.best_lap_ms && row.best_lap_ms > 0) {
        if (best === null || row.best_lap_ms < best) {
          best = row.best_lap_ms
          bestId = row.id
        }
      }
    }
    return bestId
  }, [rows])

  // ── FLIP animation ────────────────────────────────────────────
  // Map driver_id → DOM element ref
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  // Map driver_id → last measured offsetTop (before render)
  const prevTopsRef = useRef<Map<string, number>>(new Map())

  // Capture positions BEFORE render (layout effect runs sync after DOM paint)
  // We use a plain ref updated in render-time to capture before next layout
  const capturedBeforeRef = useRef(false)

  // Before each render we capture current tops
  // This runs synchronously during render of parent, so it's "before" the upcoming paint
  // We'll use useLayoutEffect in a wrapper div that fires before children repaint
  const containerRef = useRef<HTMLDivElement>(null)

  // Track which drivers changed position direction for highlight
  const prevPositionRef = useRef<Map<string, number>>(new Map())
  const [posChanges, setPosChanges] = useState<Map<string, 'up' | 'down'>>(new Map())
  const highlightTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  // Capture tops before DOM update
  useLayoutEffect(() => {
    // Save current tops before the upcoming repaint
    const map = new Map<string, number>()
    for (const [id, el] of rowRefs.current) {
      map.set(id, el.offsetTop)
    }
    prevTopsRef.current = map
  })

  // After paint: detect moves, run FLIP, detect position changes
  useLayoutEffect(() => {
    const prev = prevTopsRef.current

    for (const [id, el] of rowRefs.current) {
      const oldTop = prev.get(id)
      const newTop = el.offsetTop
      if (oldTop !== undefined && oldTop !== newTop) {
        const delta = oldTop - newTop
        // Apply inverted transform (no transition)
        el.style.transition = 'none'
        el.style.transform = `translateY(${delta}px)`
        // Force reflow
        void el.offsetTop
        // Release: animate to natural position
        el.style.transition = 'transform 500ms ease'
        el.style.transform = ''
      }
    }

    // Detect position changes for highlight
    const newChanges = new Map<string, 'up' | 'down'>()
    for (const row of rows) {
      if (row.position === null) continue
      const prev = prevPositionRef.current.get(row.id)
      if (prev !== undefined && prev !== row.position) {
        const dir = row.position < prev ? 'up' : 'down'
        newChanges.set(row.id, dir)
        // Clear after 2s
        const existing = highlightTimers.current.get(row.id)
        if (existing) clearTimeout(existing)
        const t = setTimeout(() => {
          setPosChanges((old) => {
            const next = new Map(old)
            next.delete(row.id)
            return next
          })
          highlightTimers.current.delete(row.id)
        }, 2000)
        highlightTimers.current.set(row.id, t)
      }
      prevPositionRef.current.set(row.id, row.position)
    }
    if (newChanges.size > 0) {
      setPosChanges((old) => {
        const next = new Map(old)
        for (const [k, v] of newChanges) next.set(k, v)
        return next
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows])

  return (
    <div
      ref={containerRef}
      className="col col-timing"
      style={{ '--row-count': rowCount } as React.CSSProperties}
    >
      <div className="label">TIMING</div>
      {/* Column headers */}
      <div className="trow-hdr">
        <span>POS</span>
        <span />
        <span>DRV</span>
        <span title="Gap to car ahead">INT</span>
        <span title="Gap to leader">GAP</span>
        <span title="Last lap time">LAST</span>
        <span />
        <span>TYR</span>
        <span>PIT</span>
      </div>
      {rows.map((row) => {
        const isLead = row.position === 1
        const inBattle = battleSet.has(row.id)
        const isRetired = row.retired === true
        const color = teamColor(row.id)
        const isSelected = selectedIds.includes(row.id)
        const posChange = posChanges.get(row.id)
        const trend = paceTrend(row)
        const hasFastestLap = row.id === fastestLapHolder

        const liveEst = liveGaps?.get(row.id)
        const displayInterval = liveEst?.fromTelemetry ? liveEst.interval_s : row.interval_s
        const displayGap = liveEst?.fromTelemetry ? liveEst.gap_s : row.gap_s

        const intDisplay = isRetired
          ? <span className="gap dim">OUT</span>
          : isLead
            ? <span className="gap dim">—</span>
            : displayInterval !== null && displayInterval !== undefined
              ? <span className="gap dim">{`+${displayInterval.toFixed(1)}`}</span>
              : <span className="gap dim">—</span>

        const gapDisplay = isRetired
          ? <span className="gap dim">OUT</span>
          : isLead
            ? <span className="gap dim">—</span>
            : <span className={`gap${displayGap === null || displayGap === undefined ? ' dim' : ''}`}>
                {displayGap !== null && displayGap !== undefined ? `+${displayGap.toFixed(1)}` : '—'}
              </span>

        const compound = row.tyre_compound?.charAt(0).toUpperCase() ?? '?'

        const trendEl = trend === 'up'
          ? <span className="pace-trend up" title="vs own recent pace">▲</span>
          : trend === 'down'
            ? <span className="pace-trend down" title="vs own recent pace">▼</span>
            : <span className="pace-trend" />

        return (
          <div
            key={row.id}
            ref={(el) => {
              if (el) rowRefs.current.set(row.id, el)
              else rowRefs.current.delete(row.id)
            }}
            className={[
              'trow',
              isLead ? 'lead' : '',
              inBattle ? 'battle-tick' : '',
              isRetired ? 'retired' : '',
              isSelected ? 'trow-selected' : '',
              posChange === 'up' ? 'trow-pos-up' : '',
              posChange === 'down' ? 'trow-pos-down' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => onSelectDriver(row.id)}
            style={{ cursor: 'pointer' }}
          >
            <span className="pos">{isRetired ? '—' : (row.position ?? '—')}</span>
            <span className="tbar" style={{ background: color }} />
            <span className="code">
              {row.id}
              {row.in_pit && !isRetired && <span className="pit-tag">PIT</span>}
            </span>
            {intDisplay}
            {gapDisplay}
            <span className="last-lap">
              {isRetired ? '—' : fmtLastLap(row.last_lap_ms)}
              {hasFastestLap && !isRetired && <span className="fl-dot" title="Fastest lap">●</span>}
            </span>
            {trendEl}
            <span className={`ty ${compound}`}>{isRetired ? '—' : <>{compound}<span className="age">{row.tyre_age_laps ?? '—'}</span></>}</span>
            <span className="pits-count">{row.pit_count ?? 0}</span>
          </div>
        )
      })}
      {rows.length === 0 && <div className="trow-empty">No data</div>}
    </div>
  )
})
