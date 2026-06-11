import React, { useMemo } from 'react'
import type { CommentaryItem, Insight } from '../../api/types'

type Props = {
  insights: Insight[]
  commentary: CommentaryItem[]
}

/** Stable key: strip trailing :number from insight_id, or fall back to type+drivers. */
function stableKey(ins: Insight): string {
  const stripped = ins.insight_id.replace(/:\d+$/, '')
  return stripped || `${ins.type}:${ins.driver_ids.join(',')}`
}

function insightTitle(insight: Insight): string {
  return insight.driver_ids.join(' ← ') || insight.type.replace(/_/g, ' ')
}

function insightSubtitle(insight: Insight): string {
  return `${insight.type.replace(/_/g, ' ')} · ${insight.severity.toUpperCase()}`
}

function evidenceData(insight: Insight): { label: string; value: string }[] {
  const items: { label: string; value: string }[] = []
  const ev = insight.evidence
  if (typeof ev.gap_s === 'number') items.push({ label: 'GAP', value: `${ev.gap_s.toFixed(1)}s` })
  if (typeof ev.interval_s === 'number') items.push({ label: 'INT', value: `${ev.interval_s.toFixed(2)}s` })
  if (typeof ev.pace_delta_ms === 'number')
    items.push({ label: 'Δ PACE', value: `+${(ev.pace_delta_ms / 1000).toFixed(1)}/lap` })
  if (typeof ev.tyre_age === 'number') items.push({ label: 'TYRES', value: `${ev.tyre_age} LAPS` })
  return items
}

const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }

function severityClass(severity: string): string {
  if (severity === 'high') return 'ins high'
  if (severity === 'medium') return 'ins'
  return 'ins pace'
}

const InsightCard = React.memo(function InsightCard({
  ins,
  text,
}: {
  ins: Insight
  text: string
}) {
  const data = evidenceData(ins)
  return (
    <div className={severityClass(ins.severity)}>
      <h4>
        {insightTitle(ins)}
        <small>{insightSubtitle(ins)}</small>
      </h4>
      {text && <p>{text}</p>}
      {data.length > 0 && (
        <div className="data">
          {data.map((d) => (
            <span key={d.label}>
              {d.label} <b>{d.value}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  )
})

export const InsightPanel = React.memo(function InsightPanel({ insights, commentary }: Props) {
  // Build commentary map keyed by stable key (strip trailing :ms from insight_id)
  const commentaryMap: Record<string, string> = useMemo(() => {
    const m: Record<string, string> = {}
    for (const c of commentary) {
      if (c.insight_id) {
        const key = c.insight_id.replace(/:\d+$/, '')
        m[key] = c.text
      }
    }
    return m
  }, [commentary])

  // Sort: severity desc, then stable key alphabetical; limit to 6
  const sorted = useMemo(() => {
    return [...insights]
      .sort((a, b) => {
        const sd = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
        if (sd !== 0) return sd
        return stableKey(a).localeCompare(stableKey(b))
      })
      .slice(0, 6)
  }, [insights])

  return (
    <div className="col col-insights">
      <div className="label">WHAT TO WATCH</div>
      {sorted.map((ins) => {
        const key = stableKey(ins)
        return (
          <InsightCard
            key={key}
            ins={ins}
            text={commentaryMap[key] ?? ''}
          />
        )
      })}
      {sorted.length === 0 && (
        <div className="ins pace">
          <h4>
            No active insights<small>INFO</small>
          </h4>
          <p>Waiting for race data…</p>
        </div>
      )}
    </div>
  )
})
