import { moveElement } from 'react-grid-layout'
import type { Layout, LayoutItem } from 'react-grid-layout'

export type WorkspaceMode = 'replay' | 'live'
export type DeskMode = 'classic' | 'custom'
export type DeskPreferences = Record<WorkspaceMode, DeskMode>
export type MobileCenter = 'battles' | 'track'
export type WidgetId = typeof WIDGET_IDS[number]
export type WidgetDensity = 'auto' | 'full' | 'compact' | 'summary'
export type ResolvedDensity = Exclude<WidgetDensity, 'auto'>
export type WorkspaceWidget = LayoutItem & {
  visible: boolean
  density: WidgetDensity
}
export type WorkspaceLayout = {
  version: 2
  widgets: Record<WidgetId, WorkspaceWidget>
}
export type Workspaces = {
  version: 2
  replay: WorkspaceLayout
  live: WorkspaceLayout
}

type WorkspaceStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
type WidgetDefinition = {
  label: string
  minW: number
  minH: number
  densities: readonly WidgetDensity[]
  modes: readonly WorkspaceMode[]
  initial: Pick<LayoutItem, 'x' | 'y' | 'w' | 'h'>
  visible: boolean
  anchored?: boolean
}

export const WIDGET_IDS = [
  'timing', 'battles', 'track', 'insights', 'feed',
  'strategy', 'pace', 'highlights', 'dotd',
] as const

const ALL_DENSITIES = ['auto', 'full', 'compact', 'summary'] as const
const BOTH_MODES = ['replay', 'live'] as const

export const WIDGET_REGISTRY: Record<WidgetId, WidgetDefinition> = {
  timing: {
    label: 'Timing', minW: 3, minH: 8, densities: ALL_DENSITIES, modes: BOTH_MODES,
    initial: { x: 0, y: 0, w: 3, h: 14 }, visible: true,
  },
  battles: {
    label: 'Battles', minW: 4, minH: 6, densities: ALL_DENSITIES, modes: BOTH_MODES,
    initial: { x: 3, y: 0, w: 5, h: 7 }, visible: true,
  },
  track: {
    label: 'Track', minW: 4, minH: 6, densities: ['auto', 'full'], modes: BOTH_MODES,
    initial: { x: 8, y: 0, w: 4, h: 7 }, visible: false,
  },
  insights: {
    label: 'Insights', minW: 3, minH: 6, densities: ALL_DENSITIES, modes: BOTH_MODES,
    initial: { x: 8, y: 0, w: 4, h: 14 }, visible: true,
  },
  feed: {
    label: 'Race feed', minW: 4, minH: 6, densities: ALL_DENSITIES, modes: BOTH_MODES,
    initial: { x: 3, y: 7, w: 5, h: 7 }, visible: true,
  },
  strategy: {
    label: 'Strategy', minW: 6, minH: 5, densities: ALL_DENSITIES, modes: ['replay'],
    initial: { x: 0, y: 14, w: 12, h: 6 }, visible: false,
  },
  pace: {
    label: 'Pace outlook', minW: 4, minH: 5, densities: ALL_DENSITIES, modes: BOTH_MODES,
    initial: { x: 0, y: 20, w: 8, h: 6 }, visible: false,
  },
  highlights: {
    label: 'Highlights', minW: 4, minH: 5, densities: ['auto', 'full'], modes: ['replay'],
    initial: { x: 8, y: 20, w: 4, h: 6 }, visible: false, anchored: true,
  },
  dotd: {
    label: 'Driver of the day', minW: 4, minH: 5, densities: ['auto', 'full'], modes: ['replay'],
    initial: { x: 0, y: 26, w: 6, h: 6 }, visible: false, anchored: true,
  },
}

export const WORKSPACE_KEY = 'racelens_workspace_layout_v2'
export const DESK_KEY = 'racelens_desk_mode'
export const MOBILE_CENTER_KEY = 'racelens_mobile_center'
const LEGACY_DASHBOARD_KEY = 'racelens_dashboard_layout'

function storageOrBrowser(storage?: WorkspaceStorage): WorkspaceStorage {
  return storage ?? localStorage
}

function widgetDefault(id: WidgetId, mode: WorkspaceMode): WorkspaceWidget {
  const definition = WIDGET_REGISTRY[id]
  return {
    i: id,
    ...definition.initial,
    minW: definition.minW,
    minH: definition.minH,
    visible: definition.visible && definition.modes.includes(mode),
    density: 'auto',
  }
}

export function defaultWorkspace(mode: WorkspaceMode): WorkspaceLayout {
  return {
    version: 2,
    widgets: Object.fromEntries(WIDGET_IDS.map((id) => [id, widgetDefault(id, mode)])) as Record<WidgetId, WorkspaceWidget>,
  }
}

function finite(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : fallback
}

function normalizeWorkspace(value: unknown, mode: WorkspaceMode): WorkspaceLayout {
  const fallback = defaultWorkspace(mode)
  if (!value || typeof value !== 'object') return fallback
  const stored = value as { widgets?: Record<string, Partial<WorkspaceWidget>> }
  const widgets = Object.fromEntries(WIDGET_IDS.map((id) => {
    const base = fallback.widgets[id]
    const item = stored.widgets?.[id]
    if (!item || typeof item !== 'object') return [id, base]
    const definition = WIDGET_REGISTRY[id]
    const width = Math.min(12, Math.max(definition.minW, finite(item.w, base.w)))
    const density = definition.densities.includes(item.density as WidgetDensity)
      ? item.density as WidgetDensity
      : 'auto'
    return [id, {
      ...base,
      x: Math.min(12 - width, Math.max(0, finite(item.x, base.x))),
      y: Math.max(0, finite(item.y, base.y)),
      w: width,
      h: Math.max(definition.minH, finite(item.h, base.h)),
      visible: definition.modes.includes(mode) && item.visible !== false,
      density,
    }]
  })) as Record<WidgetId, WorkspaceWidget>
  return { version: 2, widgets }
}

function migrateLegacy(storage: WorkspaceStorage): Workspaces | null {
  const raw = storage.getItem(LEGACY_DASHBOARD_KEY)
  if (!raw) return null
  try {
    const old = JSON.parse(raw) as {
      center?: 'battles' | 'track'
      timing?: boolean
      insights?: boolean
      feed?: boolean
    }
    const replay = defaultWorkspace('replay')
    replay.widgets.timing.visible = old.timing !== false
    replay.widgets.insights.visible = old.insights !== false
    replay.widgets.feed.visible = old.feed !== false
    replay.widgets.battles.visible = old.center !== 'track'
    replay.widgets.track.visible = old.center === 'track'
    storage.setItem(MOBILE_CENTER_KEY, old.center === 'track' ? 'track' : 'battles')
    return { version: 2, replay, live: defaultWorkspace('live') }
  } catch {
    return null
  }
}

export function readWorkspaces(storage?: WorkspaceStorage): Workspaces {
  try {
    const target = storageOrBrowser(storage)
    const raw = target.getItem(WORKSPACE_KEY)
    if (raw) {
      const stored = JSON.parse(raw) as Partial<Workspaces>
      if (stored.version === 2) {
        return {
          version: 2,
          replay: normalizeWorkspace(stored.replay, 'replay'),
          live: normalizeWorkspace(stored.live, 'live'),
        }
      }
    }
    const migrated = migrateLegacy(target)
    if (migrated) {
      target.setItem(WORKSPACE_KEY, JSON.stringify(migrated))
      target.removeItem(LEGACY_DASHBOARD_KEY)
      return migrated
    }
  } catch { /* use defaults */ }
  return { version: 2, replay: defaultWorkspace('replay'), live: defaultWorkspace('live') }
}

export function writeWorkspace(mode: WorkspaceMode, workspace: WorkspaceLayout, storage?: WorkspaceStorage): Workspaces {
  const target = storageOrBrowser(storage)
  const current = readWorkspaces(target)
  const next = { ...current, [mode]: normalizeWorkspace(workspace, mode) }
  try { target.setItem(WORKSPACE_KEY, JSON.stringify(next)) } catch { /* noop */ }
  return next
}

export function resetWorkspace(mode: WorkspaceMode, storage?: WorkspaceStorage): Workspaces {
  return writeWorkspace(mode, defaultWorkspace(mode), storage)
}

export function readMobileCenter(storage?: WorkspaceStorage): MobileCenter {
  try {
    const value = storageOrBrowser(storage).getItem(MOBILE_CENTER_KEY)
    return value === 'track' ? 'track' : 'battles'
  } catch {
    return 'battles'
  }
}

export function writeMobileCenter(center: MobileCenter, storage?: WorkspaceStorage): MobileCenter {
  try { storageOrBrowser(storage).setItem(MOBILE_CENTER_KEY, center) } catch { /* noop */ }
  return center
}

export function readDeskPreferences(storage?: WorkspaceStorage): DeskPreferences {
  try {
    const stored = JSON.parse(storageOrBrowser(storage).getItem(DESK_KEY) ?? '{}') as Partial<DeskPreferences>
    return {
      replay: stored.replay === 'custom' ? 'custom' : 'classic',
      live: stored.live === 'custom' ? 'custom' : 'classic',
    }
  } catch {
    return { replay: 'classic', live: 'classic' }
  }
}

export function writeDeskPreference(
  mode: WorkspaceMode,
  desk: DeskMode,
  storage?: WorkspaceStorage,
): DeskPreferences {
  const target = storageOrBrowser(storage)
  const next = { ...readDeskPreferences(target), [mode]: desk }
  try { target.setItem(DESK_KEY, JSON.stringify(next)) } catch { /* noop */ }
  return next
}

export function saveCustomWorkspace(
  mode: WorkspaceMode,
  workspace: WorkspaceLayout,
  storage?: WorkspaceStorage,
): { workspaces: Workspaces; desks: DeskPreferences } {
  return {
    workspaces: writeWorkspace(mode, workspace, storage),
    desks: writeDeskPreference(mode, 'custom', storage),
  }
}

export function updateWorkspaceWidget(
  workspace: WorkspaceLayout,
  mode: WorkspaceMode,
  id: WidgetId,
  update: Partial<WorkspaceWidget>,
): WorkspaceLayout {
  return normalizeWorkspace({
    ...workspace,
    widgets: {
      ...workspace.widgets,
      [id]: { ...workspace.widgets[id], ...update, i: id },
    },
  }, mode)
}

export function applyWorkspaceLayout(
  workspace: WorkspaceLayout,
  mode: WorkspaceMode,
  layout: Layout,
): WorkspaceLayout {
  const widgets = { ...workspace.widgets }
  for (const next of layout) {
    if (!WIDGET_IDS.includes(next.i as WidgetId)) continue
    const id = next.i as WidgetId
    widgets[id] = {
      ...widgets[id],
      x: next.x,
      y: next.y,
      w: next.w,
      h: next.h,
    }
  }
  return normalizeWorkspace({ ...workspace, widgets }, mode)
}

export function moveWorkspaceItem(
  layout: Layout,
  id: string,
  x: number,
  y: number,
): Layout {
  const nextLayout = layout.map((item) => ({ ...item }))
  const current = nextLayout.find((item) => item.i === id)
  if (!current) return nextLayout
  return moveElement(nextLayout, current, x, y, true, false, 'vertical', 12, false)
}

export function isDirectActivation(currentTarget: unknown, target: unknown): boolean {
  return currentTarget === target
}

export function selectDensity(
  width: number,
  height: number,
  supported: readonly WidgetDensity[],
  override: WidgetDensity,
): ResolvedDensity {
  if (override !== 'auto' && supported.includes(override)) return override
  if ((width < 300 || height < 180) && supported.includes('summary')) return 'summary'
  if ((width < 440 || height < 300) && supported.includes('compact')) return 'compact'
  if (supported.includes('full')) return 'full'
  return supported.includes('compact') ? 'compact' : 'summary'
}

export function toggleDriverFocus(selectedIds: string[], id: string): string[] {
  if (selectedIds.includes(id)) return selectedIds.filter((selected) => selected !== id)
  if (selectedIds.length >= 2) return [selectedIds[selectedIds.length - 1], id]
  return [...selectedIds, id]
}

type WorkspaceActionSource = 'battle' | 'strategy' | 'feed'

export function workspaceAction(
  mode: WorkspaceMode,
  source: WorkspaceActionSource,
  driverIds: string[],
  atMs?: number,
): { focusIds: string[]; seekMs: number | null } {
  const ids = [...new Set(driverIds.map((id) => id.trim()).filter(Boolean))]
  const focusIds = source === 'battle' ? ids.slice(0, 2) : ids.slice(0, 1)
  return {
    focusIds,
    seekMs: source === 'feed' && mode === 'replay' && Number.isFinite(atMs) ? atMs! : null,
  }
}
