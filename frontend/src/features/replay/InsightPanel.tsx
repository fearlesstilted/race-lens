import React from 'react'
import type { CommentaryItem, Insight } from '../../api/types'

type Props = {
  insights: Insight[]
  commentary: CommentaryItem[]
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
  const commentaryMap: Record<string, string> = {}
  for (const c of commentary) {
    if (c.insight_id) commentaryMap[c.insight_id] = c.text
  }

  return (
    <div className="col col-insights">
      <div className="label">WHAT TO WATCH</div>
      {insights.map((ins) => (
        <InsightCard
          key={ins.insight_id}
          ins={ins}
          text={commentaryMap[ins.insight_id] ?? ''}
        />
      ))}
      {insights.length === 0 && (
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
