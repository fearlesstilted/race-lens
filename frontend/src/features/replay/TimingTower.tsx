import React, { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Battle, DriverState } from '../../api/types'
import { teamColor } from './teamColors'

type DriverRow = { id: string } & DriverState

type Props = {
  rows: DriverRow[]
  battles: Battle[]
  selectedIds: string[]
  onSelectDriver: (id: string) => void
}

function fmtLastLap(ms: number | null): string {
  if (ms === null || ms <= 0) return '—'
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const millis = Math.floor(ms % 1000)
  return `${m}:${String(s).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
}

/** Pace trend: compare last_lap_ms vs mean of recent_laps_ms (fallback: best_lap_ms). */
function paceTrend(row: DriverRow): 'up' | 'down' | null {
  const last = row.last_lap_ms
  if (!last || last <= 0) return null

  const recent = row.recent_laps_ms
  let avg: number | null = null

  if (Array.isArray(recent) && recent.length > 0) {
    const valid = recent.filter((v) => v > 0)
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

  const containerRef = useRef<HTMLDivElement>(null)

  // Track which drivers changed position direction for highlight
  const prevPositionRef = useRef<Map<string, number>>(new Map())
  const [posChanges, setPosChanges] = useState<Map<string, 'up' | 'down'>>(new Map())
  const highlightTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  // After paint: detect moves, run FLIP, detect position changes
  useLayoutEffect(() => {
    const prev = prevTopsRef.current
    // Honour reduced-motion: skip transform animation entirely if the user requested it.
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    for (const [id, el] of rowRefs.current) {
      const oldTop = prev.get(id)
      const newTop = el.offsetTop
      if (oldTop !== undefined && oldTop !== newTop) {
        const delta = oldTop - newTop
        if (reducedMotion) {
          // No motion — just snap to final position (no transform trickery).
          el.style.transform = ''
          el.style.transition = 'none'
          el.style.zIndex = ''
        } else {
          // Lift above neighbours during travel so rows glide over, not through.
          el.style.zIndex = '10'
          // Apply inverted transform (no transition) — the FLIP "First" step.
          el.style.transition = 'none'
          el.style.transform = `translateY(${delta}px)`
          // Force reflow to commit the starting transform before we release.
          void el.offsetTop
          // Release with broadcast-grade easing: fast start, silky settle.
          // 310ms is short enough to feel snappy at 60fps but long enough to
          // read clearly in a GIF/screen-record.
          el.style.transition = 'transform 310ms cubic-bezier(0.2, 1, 0.3, 1), z-index 0s 310ms'
          el.style.transform = ''
          // Drop z-index back after travel completes.
          const clearZ = setTimeout(() => {
            el.style.zIndex = ''
            el.style.transition = ''
          }, 320)
          // Track so we don't leak timers (overwrite if another swap fires sooner).
          ;(el as HTMLDivElement & { _zTimer?: ReturnType<typeof setTimeout> })._zTimer && clearTimeout(
            (el as HTMLDivElement & { _zTimer?: ReturnType<typeof setTimeout> })._zTimer!
          )
          ;(el as HTMLDivElement & { _zTimer?: ReturnType<typeof setTimeout> })._zTimer = clearZ
        }
      }
    }

    // Detect position changes for highlight + position-number flash
    const newChanges = new Map<string, 'up' | 'down'>()
    for (const row of rows) {
      if (row.position === null) continue
      const prevPos = prevPositionRef.current.get(row.id)
      if (prevPos !== undefined && prevPos !== row.position) {
        const dir = row.position < prevPos ? 'up' : 'down'
        newChanges.set(row.id, dir)

        // Flash the position number badge via Web Animations API.
        if (!reducedMotion) {
          const el = rowRefs.current.get(row.id)
          const posEl = el?.querySelector<HTMLElement>('.pos')
          if (posEl) {
            posEl.animate(
              [
                { transform: 'skewX(-8deg) scale(1)',    opacity: 1   },
                { transform: 'skewX(-8deg) scale(1.22)', opacity: 1   },
                { transform: 'skewX(-8deg) scale(1)',    opacity: 0.9 },
              ],
              { duration: 280, easing: 'ease-out', fill: 'none' },
            )
          }
        }

        // Clear accent bar after 2.2s
        const existing = highlightTimers.current.get(row.id)
        if (existing) clearTimeout(existing)
        const t = setTimeout(() => {
          setPosChanges((old) => {
            const next = new Map(old)
            next.delete(row.id)
            return next
          })
          highlightTimers.current.delete(row.id)
        }, 2200)
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

    // Capture current tops for the NEXT FLIP — must run after the comparison
    // above, otherwise it overwrites the old positions and every delta is 0
    // (that was the bug: rows never moved, the number just blinked in place).
    const tops = new Map<string, number>()
    for (const [id, el] of rowRefs.current) {
      tops.set(id, el.offsetTop)
    }
    prevTopsRef.current = tops
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
        <span title="Tyre compound">TYR</span>
        <span className="col-age" title="Tyre age laps">AGE</span>
        <span title="Last lap time">LAST</span>
        <span />
        <span title="Gap to leader">GAP</span>
        <span className="col-int" title="Gap to car ahead">INT</span>
        <span className="col-pit">PIT</span>
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

        const displayInterval = row.interval_s
        const displayGap = row.gap_s

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
            <span className={`ty ${compound}`}>
              {isRetired ? '—' : compound}
            </span>
            <span className={`col-age tyre-age${!isRetired && row.tyre_age_laps != null && row.tyre_age_laps <= 2 ? ' fresh' : ''}`}>
              {isRetired ? '' : (row.tyre_age_laps ?? '—')}
            </span>
            <span className="last-lap">
              {isRetired ? '—' : fmtLastLap(row.last_lap_ms)}
              {hasFastestLap && !isRetired && <span className="fl-dot" title="Fastest lap">●</span>}
            </span>
            {trendEl}
            {gapDisplay}
            {intDisplay}
            <span className="col-pit pits-count">{row.pit_count ?? 0}</span>
          </div>
        )
      })}
      {rows.length === 0 && <div className="trow-empty">No data</div>}
    </div>
  )
})
