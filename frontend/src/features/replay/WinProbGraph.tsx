/**
 * WinProbGraph — history of an uncalibrated gap-pressure score.
 *
 * Replay: shows the history of win probability for the top-5 drivers from
 * session start up to `atMs` (spoiler-free), via GET
 * /api/sessions/{id}/win-prob-series?until_ms=&samples=20.
 *
 * Live (`live` prop): there is no history endpoint — instead each throttle
 * tick polls the single-point /api/live/win-prob mirror and appends to a
 * locally-accumulated rolling series, building the chart up as the session
 * progresses.
 *
 * Lines are drawn as SVG polylines; no chart library required.
 */
import { useEffect, useRef, useState } from 'react'
import { getLiveWinProb, getWinProbSeries } from '../../api/client'
import type { WinProbSeriesPoint } from '../../api/types'
import { teamColor } from './teamColors'

type Props = {
  sessionId?: string | null
  atMs: number
  /** Live mode: accumulate from /api/live/win-prob instead of a replay series fetch. */
  live?: boolean
}

const W = 480
const H = 140
const PAD = { top: 10, right: 52, bottom: 18, left: 34 }
const INNER_W = W - PAD.left - PAD.right
const INNER_H = H - PAD.top - PAD.bottom
const SAMPLES = 20
const MAX_LIVE_POINTS = 60
const Y_TICKS = [0, 25, 50, 75, 100]
// Throttle the series fetch because atMs changes every frame during playback.
const THROTTLE_MS = 1500

function scaleX(idx: number, total: number): number {
  if (total <= 1) return PAD.left
  return PAD.left + (idx / (total - 1)) * INNER_W
}

function scaleY(prob: number): number {
  // prob 0–1 → y from bottom
  return PAD.top + INNER_H - prob * INNER_H
}

function top5FromSeries(pts: WinProbSeriesPoint[]): string[] {
  const maxProb: Record<string, number> = {}
  for (const pt of pts) {
    for (const [d, p] of Object.entries(pt.probs)) {
      if ((maxProb[d] ?? 0) < p) maxProb[d] = p
    }
  }
  return Object.entries(maxProb)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([d]) => d)
}

export function WinProbGraph({ sessionId, atMs, live }: Props) {
  const [series, setSeries] = useState<WinProbSeriesPoint[]>([])
  const [drivers, setDrivers] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const lastFetch = useRef(0)
  const liveSeriesRef = useRef<WinProbSeriesPoint[]>([])

  // A new data source must never display the previous source's series.
  useEffect(() => {
    liveSeriesRef.current = []
    setSeries([])
    setDrivers([])
    lastFetch.current = 0
  }, [sessionId, live])

  useEffect(() => {
    if (!live && atMs === 0) return
    let cancelled = false

    const run = () => {
      lastFetch.current = Date.now()
      setLoading(true)
      const req = live
        ? getLiveWinProb().then((wp) => {
            const last = liveSeriesRef.current[liveSeriesRef.current.length - 1]
            if (!last || last.at_ms !== wp.at_ms) {
              liveSeriesRef.current = [...liveSeriesRef.current, { at_ms: wp.at_ms, probs: wp.win_prob }]
                .slice(-MAX_LIVE_POINTS)
            }
            return liveSeriesRef.current
          })
        : sessionId
          ? getWinProbSeries(sessionId, atMs, SAMPLES)
          : Promise.resolve<WinProbSeriesPoint[]>([])

      req
        .then((pts) => {
          if (cancelled) return
          setSeries(pts)
          setDrivers(top5FromSeries(pts))
          setLoading(false)
        })
        .catch(() => {
          if (!cancelled) {
            setSeries([])
            setDrivers([])
            setLoading(false)
          }
        })
    }

    const elapsed = Date.now() - lastFetch.current
    if (elapsed >= THROTTLE_MS) {
      run()
      return () => { cancelled = true }
    }
    const t = setTimeout(run, THROTTLE_MS - elapsed)
    return () => { cancelled = true; clearTimeout(t) }
  }, [sessionId, atMs, live])

  const n = series.length

  return (
    <div className="win-prob-graph">
      <div className="win-prob-label">GAP PRESSURE SCORE · UNCALIBRATED</div>
      {loading && <div className="win-prob-loading">…</div>}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="win-prob-svg"
        aria-label="Gap pressure score over time"
      >
        {/* Hairline grid */}
        {Y_TICKS.map((t) => {
          const y = scaleY(t / 100)
          return (
            <g key={t}>
              <line
                x1={PAD.left}
                y1={y}
                x2={PAD.left + INNER_W}
                y2={y}
                stroke="#ffffff14"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 4}
                y={y + 3.5}
                textAnchor="end"
                className="win-prob-axis"
              >
                {t}
              </text>
            </g>
          )
        })}

        {/* Driver lines */}
        {n >= 2 && drivers.map((d) => {
          const pts = series
            .map((pt, i) => {
              const p = pt.probs[d] ?? 0
              return `${scaleX(i, n).toFixed(1)},${scaleY(p).toFixed(1)}`
            })
            .join(' ')
          return (
            <polyline
              key={d}
              points={pts}
              fill="none"
              stroke={teamColor(d)}
              strokeWidth={1.5}
              strokeLinejoin="round"
              opacity={0.9}
            />
          )
        })}

        {/* Right-side driver labels at final point */}
        {n >= 1 && drivers.map((d) => {
          const lastProb = series[n - 1]?.probs[d] ?? 0
          const y = scaleY(lastProb)
          return (
            <text
              key={`lbl-${d}`}
              x={PAD.left + INNER_W + 4}
              y={y + 3.5}
              fill={teamColor(d)}
              className="win-prob-driver"
            >
              {d}
            </text>
          )
        })}
      </svg>
    </div>
  )
}
