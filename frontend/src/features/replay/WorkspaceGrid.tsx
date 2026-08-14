import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactGridLayout, { useContainerWidth, verticalCompactor } from 'react-grid-layout'
import type { KeyboardEvent, ReactNode } from 'react'
import type { Layout, LayoutItem } from 'react-grid-layout'
import {
  WIDGET_IDS,
  WIDGET_REGISTRY,
  applyWorkspaceLayout,
  moveWorkspaceItem,
  selectDensity,
  updateWorkspaceWidget,
} from './workspace'
import type {
  WidgetId,
  WidgetDensity,
  WorkspaceLayout,
  WorkspaceMode,
  WorkspaceWidget,
} from './workspace'

type Props = {
  mode: WorkspaceMode
  workspace: WorkspaceLayout
  editing: boolean
  widgets: Partial<Record<WidgetId, ReactNode>>
  onChange: (workspace: WorkspaceLayout) => void
  onDone: () => void
  onReset: () => void
}

const sameGridItem = (a: WorkspaceWidget, b: LayoutItem) => (
  a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h
)

const gridItem = (item: WorkspaceWidget): LayoutItem => ({
  i: item.i,
  x: item.x,
  y: item.y,
  w: item.w,
  h: item.h,
  minW: item.minW,
  minH: item.minH,
})

function WorkspaceFrame({
  id,
  item,
  editing,
  onHide,
  onDensity,
  onKeyDown,
  children,
}: {
  id: WidgetId
  item: WorkspaceWidget
  editing: boolean
  onHide: () => void
  onDensity: (density: WidgetDensity) => void
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void
  children: ReactNode
}) {
  const frame = useRef<HTMLElement>(null)
  const [size, setSize] = useState({ width: 1000, height: 1000 })

  useEffect(() => {
    if (!frame.current) return
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(frame.current)
    return () => observer.disconnect()
  }, [])

  const definition = WIDGET_REGISTRY[id]
  const density = selectDensity(size.width, size.height, definition.densities, item.density)

  return (
    <section ref={frame} className={`workspace-widget workspace-widget--${id}`} data-density={density} aria-label={`${definition.label} widget`}>
      {editing && (
        <header
          className="workspace-widget-header workspace-drag-handle"
          tabIndex={0}
          onKeyDown={onKeyDown}
          aria-label={`${definition.label}. Arrow keys move; Shift plus arrow keys resize.`}
        >
          <span className="workspace-grip" aria-hidden="true">⠿</span>
          <strong>{definition.label}</strong>
          <label className="workspace-density workspace-control">
            <span className="sr-only">{definition.label} density</span>
            <select value={item.density} onChange={(event) => onDensity(event.target.value as WidgetDensity)}>
              {definition.densities.map((value) => (
                <option value={value} key={value}>{value.toUpperCase()}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="workspace-widget-hide workspace-control"
            onClick={onHide}
            aria-label={`Hide ${definition.label}`}
            title={`Hide ${definition.label}`}
          >×</button>
        </header>
      )}
      <div className="workspace-widget-content">{children}</div>
    </section>
  )
}

export function WorkspaceGrid({ mode, workspace, editing, widgets, onChange, onDone, onReset }: Props) {
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1600 })
  const visibleIds = useMemo(() => WIDGET_IDS.filter((id) => (
    workspace.widgets[id].visible
    && WIDGET_REGISTRY[id].modes.includes(mode)
    && widgets[id] !== undefined
  )), [mode, widgets, workspace.widgets])
  const layout = useMemo<Layout>(
    () => visibleIds.map((id) => gridItem(workspace.widgets[id])),
    [visibleIds, workspace.widgets],
  )
  const hiddenIds = useMemo(() => WIDGET_IDS.filter((id) => (
    !workspace.widgets[id].visible
    && WIDGET_REGISTRY[id].modes.includes(mode)
    && widgets[id] !== undefined
  )), [mode, widgets, workspace.widgets])

  const applyLayout = useCallback((nextLayout: Layout) => {
    if (nextLayout.every((next) => sameGridItem(workspace.widgets[next.i as WidgetId], next))) return
    onChange(applyWorkspaceLayout(workspace, mode, nextLayout))
  }, [mode, onChange, workspace])

  const handleKeyboard = useCallback((id: WidgetId, event: KeyboardEvent<HTMLElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const current = workspace.widgets[id]
    const dx = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
    const dy = event.key === 'ArrowUp' ? -1 : event.key === 'ArrowDown' ? 1 : 0
    if (event.shiftKey) {
      const minW = current.minW ?? 1
      const minH = current.minH ?? 1
      const w = Math.min(12 - current.x, Math.max(minW, current.w + dx))
      const h = Math.max(minH, current.h + dy)
      const changed = { ...gridItem(current), w, h }
      applyLayout(verticalCompactor.compact(
        layout.map((item) => item.i === id ? changed : item),
        12,
      ))
      return
    }
    applyLayout(moveWorkspaceItem(
      layout,
      id,
      Math.min(12 - current.w, Math.max(0, current.x + dx)),
      Math.max(0, current.y + dy),
    ))
  }, [applyLayout, layout, workspace.widgets])

  return (
    <div ref={containerRef} className={`workspace-grid-wrap${editing ? ' is-editing' : ' is-locked'}`}>
      {editing && (
        <div className="workspace-editbar" role="toolbar" aria-label="Custom desk editor">
          <strong>EDIT CUSTOM</strong>
          {hiddenIds.length > 0 && <span>RESTORE</span>}
          {hiddenIds.map((id) => (
            <button
              type="button"
              className="b"
              key={id}
              onClick={() => onChange(updateWorkspaceWidget(workspace, mode, id, { visible: true }))}
            >{WIDGET_REGISTRY[id].label.toUpperCase()}</button>
          ))}
          <button type="button" className="b workspace-edit-reset" onClick={onReset}>RESET</button>
          <button type="button" className="b primary" onClick={onDone}>DONE</button>
        </div>
      )}
      {mounted && (
        <ReactGridLayout
          className="workspace-grid-canvas"
          width={width}
          layout={layout}
          gridConfig={{ cols: 12, rowHeight: 36, margin: [8, 8], containerPadding: [12, 8] }}
          dragConfig={{ enabled: editing, handle: '.workspace-drag-handle', cancel: '.workspace-control', bounded: true }}
          resizeConfig={{ enabled: editing, handles: ['se'] }}
          compactor={verticalCompactor}
          onLayoutChange={editing ? applyLayout : undefined}
        >
          {visibleIds.map((id) => (
            <div key={id}>
              <WorkspaceFrame
                id={id}
                item={workspace.widgets[id]}
                editing={editing}
                onHide={() => onChange(updateWorkspaceWidget(workspace, mode, id, { visible: false }))}
                onDensity={(density) => onChange(updateWorkspaceWidget(workspace, mode, id, { density }))}
                onKeyDown={(event) => handleKeyboard(id, event)}
              >
                {widgets[id]}
              </WorkspaceFrame>
            </div>
          ))}
        </ReactGridLayout>
      )}
    </div>
  )
}
