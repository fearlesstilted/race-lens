import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { CommentaryItem, Insight } from '../../api/types'

type Props = {
  insights: Insight[]
  commentary: CommentaryItem[]
  selectedIds?: string[]
}

/** Minimum wall-time a card must be displayed before it can be removed. */
const MIN_VISIBLE_MS = 6000
/** Consecutive absent updates before a card is removed. */
const ABSENT_THRESHOLD = 2

/** Stable key: strip trailing :number from insight_id, or fall back to type+drivers. */
function stableKey(ins: Insight): string {
  const stripped = ins.insight_id.replace(/:\d+$/, '')
  return stripped || `${ins.type}:${ins.driver_ids.join(',')}`
}

// Short human labels instead of raw enum names; severity is rendered once, separately
const TYPE_LABELS: Array<[string, string]> = [
  ['TRAFFIC_RISK', 'TRAFFIC'],
  ['DRS_TRAIN', 'DRS TRAIN'],
  ['PIT_WINDOW', 'PIT WINDOW'],
  ['UNDERCUT_RISK', 'UNDERCUT'],
  ['DEGRADATION_TREND', 'TYRE DEG'],
  ['CLEAN_AIR_PACE', 'CLEAN AIR'],
  ['BATTLE_DETECTED', 'BATTLE'],
]

function baseLabel(type: string): string {
  const hit = TYPE_LABELS.find(([prefix]) => type.startsWith(prefix))
  return hit ? hit[1] : type.replace(/_/g, ' ')
}

function insightTitle(insight: Insight): string {
  return insight.driver_ids.join(' ← ') || baseLabel(insight.type)
}

function insightSubtitle(insight: Insight): string {
  const label = baseLabel(insight.type)
  // severity already speaks through the edge colour; spell it out only for HIGH
  return insight.severity === 'high' ? `${label} · HIGH` : label
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

type CardState = {
  ins: Insight
  text: string
  appearedAt: number  // wall-clock ms when card first appeared
  absentCount: number // consecutive data updates where insight was absent
  leaving: boolean
}

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

  // Sort incoming insights: focused first, then severity desc, then stable key alphabetical.
  // Diversity cap: max 2 cards of the same type. Candidate list (up to 8) for hysteresis to trim.
  const incomingCandidates = useMemo(() => {
    const ranked = [...insights].sort((a, b) => {
      const af = isFocused(a) ? 0 : 1
      const bf = isFocused(b) ? 0 : 1
      if (af !== bf) return af - bf
      const sd = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      if (sd !== 0) return sd
      return stableKey(a).localeCompare(stableKey(b))
    })
    const perType: Record<string, number> = {}
    const picked: Insight[] = []
    for (const ins of ranked) {
      const label = baseLabel(ins.type)
      const count = perType[label] ?? 0
      if (count >= 2 && !isFocused(ins)) continue
      perType[label] = count + 1
      picked.push(ins)
      if (picked.length >= 8) break
    }
    return picked
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insights, selectedIds])

  // Hysteresis state: map of stable key → CardState
  const cardsRef = useRef<Map<string, CardState>>(new Map())
  const [renderTick, forceRender] = useState(0)

  useEffect(() => {
    const now = Date.now()
    const incomingKeys = new Set(incomingCandidates.map(stableKey))
    const cards = cardsRef.current

    // Update absent counts and remove cards that have been absent long enough
    // and have also expired their minimum display time
    for (const [key, card] of cards) {
      if (!incomingKeys.has(key)) {
        card.absentCount += 1
        const ageMs = now - card.appearedAt
        const minExpired = ageMs >= MIN_VISIBLE_MS
        if (card.absentCount >= ABSENT_THRESHOLD && minExpired) {
          // Mark leaving for animation, schedule removal
          if (!card.leaving) {
            card.leaving = true
            window.setTimeout(() => {
              cardsRef.current.delete(key)
              forceRender((n) => n + 1)
            }, 400)
          }
        }
      } else {
        // Insight is present again — reset absent count, update data
        card.absentCount = 0
        card.leaving = false
      }
    }

    // Update text for existing cards from commentary
    for (const [key, card] of cards) {
      const newText = commentaryMap[key] ?? card.text
      if (newText !== card.text) card.text = newText
    }

    // Add new cards for incoming insights not yet tracked
    for (const ins of incomingCandidates) {
      const key = stableKey(ins)
      if (!cards.has(key)) {
        cards.set(key, {
          ins,
          text: commentaryMap[key] ?? '',
          appearedAt: now,
          absentCount: 0,
          leaving: false,
        })
      } else {
        // Update insight data
        const card = cards.get(key)!
        card.ins = ins
        card.text = commentaryMap[key] ?? card.text
      }
    }

    // Enforce 4-card limit: cards that have expired MIN_VISIBLE_MS evict first,
    // then newest arrivals (by appearedAt desc)
    const activeCards = [...cards.entries()].filter(([, c]) => !c.leaving)
    if (activeCards.length > 4) {
      // Sort: expired-min first (can be evicted), then by newest (evict newest if needed)
      const sorted = activeCards.sort(([, a], [, b]) => {
        const aExpired = (now - a.appearedAt) >= MIN_VISIBLE_MS ? 0 : 1
        const bExpired = (now - b.appearedAt) >= MIN_VISIBLE_MS ? 0 : 1
        if (aExpired !== bExpired) return bExpired - aExpired // expired comes first (evict first)
        // Among same expiry group, newer cards evict first
        return b.appearedAt - a.appearedAt
      })
      const toEvict = sorted.slice(4)
      for (const [key, card] of toEvict) {
        if (!card.leaving) {
          card.leaving = true
          window.setTimeout(() => {
            cardsRef.current.delete(key)
            forceRender((n) => n + 1)
          }, 400)
        }
      }
    }

    forceRender((n) => n + 1)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomingCandidates, commentaryMap])

  const displayItems = useMemo(() => {
    const cards = cardsRef.current
    return [...cards.entries()].map(([key, card]) => ({
      key,
      ins: card.ins,
      text: card.text,
      leaving: card.leaving,
      focused: isFocused(card.ins),
    }))
  // renderTick ensures this re-derives after forceRender calls
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderTick, selectedIds])

  const hasVisible = displayItems.some((item) => !item.leaving)

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
      {!hasVisible && displayItems.length === 0 && (
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
