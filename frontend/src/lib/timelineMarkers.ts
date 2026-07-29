import type { RaceMarker } from '../api/types'

const CLUSTER_THRESHOLD_PCT = 1.5
const CLUSTER_MAX_SPAN_MS = 15_000

export type MarkerCluster = {
  pct: number
  items: RaceMarker[]
}

export function clusterMarkers(
  markers: RaceMarker[],
  pctFn: (marker: RaceMarker) => number,
): MarkerCluster[] {
  const groups: MarkerCluster[] = []
  for (const marker of [...markers].sort((a, b) => a.at_ms - b.at_ms)) {
    const pct = pctFn(marker)
    const last = groups[groups.length - 1]
    const firstAtMs = last?.items[0]?.at_ms
    if (
      last
      && pct - last.pct < CLUSTER_THRESHOLD_PCT
      && firstAtMs !== undefined
      && marker.at_ms - firstAtMs <= CLUSTER_MAX_SPAN_MS
    ) {
      last.items.push(marker)
    } else {
      groups.push({ pct, items: [marker] })
    }
  }
  return groups
}
