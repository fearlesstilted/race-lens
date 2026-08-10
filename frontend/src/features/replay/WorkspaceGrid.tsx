import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactGridLayout, { moveElement, useContainerWidth, verticalCompactor } from 'react-grid-layout'
import type { KeyboardEvent, ReactNode } from 'react'
import type { Layout, LayoutItem } from 'react-grid-layout'
import {
  WIDGET_IDS,
  WIDGET_REGISTRY,
  selectDensity,
  updateWorkspaceWidget,
} from './workspace'
import type {
  WidgetId,
  WorkspaceLayout,
  WorkspaceMode,
  WorkspaceWidget,
} from './workspace'

type Props = {
  mode: WorkspaceMode
  workspace: WorkspaceLayout
  widgets: Partial<Record<WidgetId, ReactNode>>
  onChange: (workspace: WorkspaceLayout) => void
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
  onHide,
  onKeyDown,
  children,
}: {
  id: WidgetId
  item: WorkspaceWidget
  onHide: () => void
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
    <section ref={frame} className="workspace-widget" data-density={density} aria-label={`${definition.label} widget`}>
      <header
        className="workspace-widget-header workspace-drag-handle"
        tabIndex={0}
        onKeyDown={onKeyDown}
        aria-label={`${definition.label}. Arrow keys move; Shift plus arrow keys resize.`}
      >
        <span className="workspace-grip" aria-hidden="true">⠿</span>
        <strong>{definition.label}</strong>
        <small>{density}</small>
        <button
          type="button"
          className="workspace-widget-hide workspace-control"
          onClick={onHide}
          aria-label={`Hide ${definition.label}`}
          title={`Hide ${definition.label}`}
        >×</button>
      </header>
      <div className="workspace-widget-content">{children}</div>
    </section>
  )
}

export function WorkspaceGrid({ mode, workspace, widgets, onChange }: Props) {
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

  const applyLayout = useCallback((nextLayout: Layout) => {
    if (nextLayout.every((next) => sameGridItem(workspace.widgets[next.i as WidgetId], next))) return
    const nextWidgets = { ...workspace.widgets }
    for (const next of nextLayout) {
      const id = next.i as WidgetId
      nextWidgets[id] = {
        ...nextWidgets[id],
        x: next.x,
        y: next.y,
        w: next.w,
        h: next.h,
      }
    }
    onChange({ ...workspace, widgets: nextWidgets })
  }, [onChange, workspace])

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
    applyLayout(moveElement(
      layout,
      gridItem(current),
      Math.min(12 - current.w, Math.max(0, current.x + dx)),
      Math.max(0, current.y + dy),
      true,
      false,
      'vertical',
      12,
      false,
    ))
  }, [applyLayout, layout, workspace.widgets])

  return (
    <div ref={containerRef} className="workspace-grid-wrap">
      {mounted && (
        <ReactGridLayout
          width={width}
          layout={layout}
          gridConfig={{ cols: 12, rowHeight: 36, margin: [8, 8], containerPadding: [12, 8] }}
          dragConfig={{ handle: '.workspace-drag-handle', cancel: '.workspace-control', bounded: true }}
          resizeConfig={{ handles: ['se'] }}
          compactor={verticalCompactor}
          onLayoutChange={applyLayout}
        >
          {visibleIds.map((id) => (
            <div key={id}>
              <WorkspaceFrame
                id={id}
                item={workspace.widgets[id]}
                onHide={() => onChange(updateWorkspaceWidget(workspace, mode, id, { visible: false }))}
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
