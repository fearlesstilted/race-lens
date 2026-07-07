/** Shared state setters passed from useReplay into its sub-hooks. */
import type { Battle, CommentaryItem, FeedItem, Insight, RaceState, RecentPass } from '../../api/types'

export type ReplaySetters = {
  setState: (s: RaceState) => void
  setInsights: (i: Insight[]) => void
  setBattles: (b: Battle[]) => void
  setRecentPasses: (p: RecentPass[]) => void
  setFeed: (f: FeedItem[]) => void
  setCommentary: (c: CommentaryItem[]) => void
  setAtMs: (ms: number) => void
  setLoading: (b: boolean) => void
  setError: (e: string | null) => void
  setFeedError: (e: string | null) => void
  setPlaying: (b: boolean) => void
}
