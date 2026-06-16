import React, { useEffect, useMemo, useRef, useState } from 'react'
import { getOvertake } from '../../api/client'
import type { CommentaryItem, Insight } from '../../api/types'

type Props = {
  insights: Insight[]
  commentary: CommentaryItem[]
  selectedIds?: string[]
  sessionStatus?: string
  /** Session ID for overtake % endpoint (replay only). */
  sessionId?: string | null
  atMs?: number
}

/** Cache overtake probabilities keyed by "ahead:behind" */
const overtakeCache = new Map<string, number>()

const MIN_VISIBLE_MS = 6000
const ABSENT_THRESHOLD = 2

function stableKey(ins: Insight): string {
  const stripped = ins.insight_id.replace(/:\d+$/, '')
  return stripped || `${ins.type}:${ins.driver_ids.join(',')}`
}

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

/** Canonical pair key: sorted driver IDs joined. */
function pairKey(ins: Insight): string {
  return [...ins.driver_ids].sort().join(':')
}

/** Group insights by driver pair. Return the best per pair + 'also' list. */
function groupByPair(insights: Insight[]): {
  primary: Insight
  also: string[]
}[] {
  const byPair = new Map<string, Insight[]>()
  for (const ins of insights) {
    const key = pairKey(ins)
    const arr = byPair.get(key) ?? []
    arr.push(ins)
    byPair.set(key, arr)
  }
  const result: { primary: Insight; also: string[] }[] = []
  for (const [, group] of byPair) {
    // Sort by severity — best first
    group.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9))
    const [primary, ...rest] = group
    result.push({
      primary,
      also: rest.map((r) => baseLabel(r.type)),
    })
  }
  return result
}

/** Grouped SC_PIT_WINDOW card — shown first under neutralization */
const ScPitWindowCard = React.memo(function ScPitWindowCard({
  drivers,
}: {
  drivers: string[]
}) {
  return (
    <div className="ins ins-sc-pit">
      <h4>
        PIT NOW
        <small>SC PIT WINDOW</small>
      </h4>
      <p>
        {drivers.join(', ')} — cheap stop under SC
      </p>
    </div>
  )
})

const InsightCard = React.memo(function InsightCard({
  ins,
  also,
  text,
  leaving,
  focused,
  overtakePct,
}: {
  ins: Insight
  also: string[]
  text: string
  leaving: boolean
  focused: boolean
  overtakePct?: number | null
}) {
  const data = evidenceData(ins)
  return (
    <div
      className={[
        severityClass(ins.severity),
        leaving ? 'ins-leaving' : 'ins-entering',
        focused ? 'ins-focused' : '',
      ].filter(Boolean).join(' ')}
    >
      <h4>
        {insightTitle(ins)}
        <small>{insightSubtitle(ins)}</small>
      </h4>
      {also.length > 0 && (
        <div className="ins-also">also: {also.join(' · ')}</div>
      )}
      {text && <p>{text}</p>}
      {overtakePct !== null && overtakePct !== undefined && (
        <div className="ins-overtake">OVERTAKE NEXT LAP: {Math.round(overtakePct * 100)}%</div>
      )}
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
  also: string[]
  text: string
  appearedAt: number
  absentCount: number
  leaving: boolean
  overtakePct: number | null
}

const NEUTRAL_STATUSES = new Set(['safety_car', 'vsc', 'red_flag'])

function isBattleType(type: string): boolean {
  return type.startsWith('BATTLE') || type.startsWith('TRAFFIC')
}

export const InsightPanel = React.memo(function InsightPanel({ insights, commentary, selectedIds = [], sessionStatus = '', sessionId, atMs = 0 }: Props) {
  const isNeutral = NEUTRAL_STATUSES.has(sessionStatus)
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

  // Follow-mode: 1 selected → insight must involve that driver as subject;
  // 2 selected → insight must involve BOTH (head-to-head pair only)
  const isFocused = (ins: Insight) => {
    if (selectedIds.length === 0) return false
    if (selectedIds.length === 1) {
      // "follow" mode: driver must be the primary subject (first id) or sole id
      return ins.driver_ids.includes(selectedIds[0])
    }
    // 2 selected: only highlight if insight involves BOTH selected drivers
    return selectedIds.every((id) => ins.driver_ids.includes(id))
  }

  // Collect all SC_PIT_WINDOW driver IDs (deduplicated) for grouped card
  const scPitDrivers = useMemo(() => {
    if (!isNeutral) return []
    const seen = new Set<string>()
    const drivers: string[] = []
    for (const ins of insights) {
      if (ins.type.startsWith('SC_PIT_WINDOW')) {
        for (const d of ins.driver_ids) {
          if (!seen.has(d)) { seen.add(d); drivers.push(d) }
        }
      }
    }
    return drivers
  }, [insights, isNeutral])

  // Sort, then group by pair, then rank groups (excluding SC_PIT_WINDOW when grouped)
  const incomingGroups = useMemo(() => {
    const filtered = isNeutral ? insights.filter((ins) => !ins.type.startsWith('SC_PIT_WINDOW')) : insights
    const ranked = [...filtered].sort((a, b) => {
      const af = isFocused(a) ? 0 : 1
      const bf = isFocused(b) ? 0 : 1
      if (af !== bf) return af - bf
      const sd = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      if (sd !== 0) return sd
      return stableKey(a).localeCompare(stableKey(b))
    })
    const groups = groupByPair(ranked)
    // Re-sort groups by their primary insight's rank
    groups.sort((ga, gb) => {
      const af = isFocused(ga.primary) ? 0 : 1
      const bf = isFocused(gb.primary) ? 0 : 1
      if (af !== bf) return af - bf
      return (SEVERITY_ORDER[ga.primary.severity] ?? 9) - (SEVERITY_ORDER[gb.primary.severity] ?? 9)
    })
    return groups.slice(0, 4)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insights, selectedIds])

  const cardsRef = useRef<Map<string, CardState>>(new Map())
  const [renderTick, forceRender] = useState(0)

  useEffect(() => {
    const now = Date.now()
    const incomingKeys = new Set(incomingGroups.map((g) => stableKey(g.primary)))
    const cards = cardsRef.current

    for (const [key, card] of cards) {
      if (!incomingKeys.has(key)) {
        card.absentCount += 1
        const ageMs = now - card.appearedAt
        const minExpired = ageMs >= MIN_VISIBLE_MS
        if (card.absentCount >= ABSENT_THRESHOLD && minExpired) {
          if (!card.leaving) {
            card.leaving = true
            window.setTimeout(() => {
              cardsRef.current.delete(key)
              forceRender((n) => n + 1)
            }, 400)
          }
        }
      } else {
        card.absentCount = 0
        card.leaving = false
      }
    }

    for (const [key, card] of cards) {
      const newText = commentaryMap[key] ?? card.text
      if (newText !== card.text) card.text = newText
    }

    for (const group of incomingGroups) {
      const key = stableKey(group.primary)
      if (!cards.has(key)) {
        cards.set(key, {
          ins: group.primary,
          also: group.also,
          text: commentaryMap[key] ?? '',
          appearedAt: now,
          absentCount: 0,
          leaving: false,
          overtakePct: null,
        })
        // Fetch overtake % for battle/traffic cards with 2 drivers
        if (sessionId && isBattleType(group.primary.type) && group.primary.driver_ids.length === 2) {
          const [ahead, behind] = group.primary.driver_ids
          const cacheKey = `${ahead}:${behind}`
          if (overtakeCache.has(cacheKey)) {
            const card = cards.get(key)
            if (card) card.overtakePct = overtakeCache.get(cacheKey)!
          } else {
            getOvertake(sessionId, atMs, ahead, behind)
              .then((res) => {
                if (!res.error) {
                  overtakeCache.set(cacheKey, res.probability)
                  const c = cardsRef.current.get(key)
                  if (c) { c.overtakePct = res.probability; forceRender((n) => n + 1) }
                }
              })
              .catch(() => undefined)
          }
        }
      } else {
        const card = cards.get(key)!
        card.ins = group.primary
        card.also = group.also
        card.text = commentaryMap[key] ?? card.text
      }
    }

    // Enforce 3 non-focused + 1 focused limit (total 4 max)
    const focusedCards = [...cards.entries()].filter(([, c]) => !c.leaving && isFocused(c.ins))
    const nonFocusedCards = [...cards.entries()].filter(([, c]) => !c.leaving && !isFocused(c.ins))
    // Allow 1 focused + 3 non-focused = 4 total
    const keepFocused = focusedCards.slice(0, 1)
    const keepNonFocused = nonFocusedCards.slice(0, 3)
    const keepKeys = new Set([...keepFocused, ...keepNonFocused].map(([k]) => k))
    const activeCards = [...cards.entries()].filter(([, c]) => !c.leaving)
    for (const [key, card] of activeCards) {
      if (!keepKeys.has(key) && !card.leaving) {
        const age = now - card.appearedAt
        if (age >= MIN_VISIBLE_MS) {
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
  }, [incomingGroups, commentaryMap])

  const displayItems = useMemo(() => {
    const cards = cardsRef.current
    return [...cards.entries()].map(([key, card]) => ({
      key,
      ins: card.ins,
      also: card.also,
      text: card.text,
      leaving: card.leaving,
      focused: isFocused(card.ins),
      overtakePct: card.overtakePct,
    }))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderTick, selectedIds])

  const hasVisible = displayItems.some((item) => !item.leaving)

  return (
    <div className="col col-insights">
      <div className="label">WHAT TO WATCH</div>
      {scPitDrivers.length > 0 && (
        <ScPitWindowCard drivers={scPitDrivers} />
      )}
      {displayItems.map(({ key, ins, also, text, leaving, focused, overtakePct }) => (
        <InsightCard
          key={key}
          ins={ins}
          also={also}
          text={text}
          leaving={leaving}
          focused={focused}
          overtakePct={overtakePct}
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
