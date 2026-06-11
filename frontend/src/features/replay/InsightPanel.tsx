import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { CommentaryItem, Insight } from '../../api/types'

type Props = {
  insights: Insight[]
  commentary: CommentaryItem[]
  selectedIds?: string[]
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
  leaving,
  focused,
}: {
  ins: Insight
  text: string
  leaving: boolean
  focused: boolean
}) {
  const data = evidenceData(ins)
  return (
    <div className={[severityClass(ins.severity), leaving ? 'ins-leaving' : 'ins-entering', focused ? 'ins-focused' : ''].filter(Boolean).join(' ')}>
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

export const InsightPanel = React.memo(function InsightPanel({ insights, commentary, selectedIds = [] }: Props) {
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

  // Helper: does this insight involve any selected driver?
  const isFocused = (ins: Insight) =>
    selectedIds.length > 0 && ins.driver_ids.some((id) => selectedIds.includes(id))

  // Sort: focused first, then severity desc, then stable key alphabetical; limit to 4
  const sorted = useMemo(() => {
    return [...insights]
      .sort((a, b) => {
        const af = isFocused(a) ? 0 : 1
        const bf = isFocused(b) ? 0 : 1
        if (af !== bf) return af - bf
        const sd = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
        if (sd !== 0) return sd
        return stableKey(a).localeCompare(stableKey(b))
      })
      .slice(0, 4)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insights, selectedIds])

  // CSS-only enter/leave animation: track which keys are "leaving"
  const prevKeysRef = useRef<Set<string>>(new Set())
  const [leavingKeys, setLeavingKeys] = useState<Set<string>>(new Set())

  useEffect(() => {
    const newKeys = new Set(sorted.map(stableKey))
    const gone = [...prevKeysRef.current].filter((k) => !newKeys.has(k))
    if (gone.length > 0) {
      setLeavingKeys((prev) => new Set([...prev, ...gone]))
      const timer = window.setTimeout(() => {
        setLeavingKeys((prev) => {
          const next = new Set(prev)
          for (const k of gone) next.delete(k)
          return next
        })
      }, 400)
      return () => clearTimeout(timer)
    }
    prevKeysRef.current = newKeys
  }, [sorted])

  // Combine current + leaving (leaving cards retain their last known data)
  const prevInsightsRef = useRef<Map<string, { ins: Insight; text: string }>>(new Map())
  const displayItems = useMemo(() => {
    const items: Array<{ key: string; ins: Insight; text: string; leaving: boolean; focused: boolean }> = []
    for (const ins of sorted) {
      const key = stableKey(ins)
      const text = commentaryMap[key] ?? ''
      prevInsightsRef.current.set(key, { ins, text })
      items.push({ key, ins, text, leaving: false, focused: isFocused(ins) })
    }
    for (const key of leavingKeys) {
      const cached = prevInsightsRef.current.get(key)
      if (cached) {
        items.push({ key, ins: cached.ins, text: cached.text, leaving: true, focused: false })
      }
    }
    return items
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted, commentaryMap, leavingKeys, selectedIds])

  return (
    <div className="col col-insights">
      <div className="label">WHAT TO WATCH</div>
      {displayItems.map(({ key, ins, text, leaving, focused }) => (
        <InsightCard
          key={key}
          ins={ins}
          text={text}
          leaving={leaving}
          focused={focused}
        />
      ))}
      {sorted.length === 0 && leavingKeys.size === 0 && (
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
