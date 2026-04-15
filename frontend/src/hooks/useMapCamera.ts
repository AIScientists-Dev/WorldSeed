/* WorldSeed — Map camera hook: Figma-style pan/zoom */
import { useRef, useCallback } from 'react'

export function useMapCamera(
  viewportRef: React.RefObject<HTMLElement | null>,
  canvasRef: React.RefObject<HTMLElement | null>,
) {
  const camera = useRef({ x: 0, y: 0, zoom: 1 })
  const dragging = useRef(false)
  const dragLast = useRef({ x: 0, y: 0 })
  const isSetup = useRef(false)
  const handlers = useRef<{
    wheel: ((e: WheelEvent) => void) | null
    mousedown: ((e: MouseEvent) => void) | null
    move: ((e: MouseEvent) => void) | null
    up: (() => void) | null
    gStart: ((e: Event) => void) | null
    gChange: ((e: Event) => void) | null
  }>({ wheel: null, mousedown: null, move: null, up: null, gStart: null, gChange: null })

  const applyCamera = useCallback(() => {
    if (!canvasRef.current) return
    const c = camera.current
    canvasRef.current.style.transform = `translate(${c.x}px, ${c.y}px) scale(${c.zoom})`
    canvasRef.current.style.transformOrigin = '0 0'
  }, [canvasRef])

  const centerView = useCallback((
    _layout?: Record<string, any>,
    inset?: { top?: number; bottom?: number },
    animate?: boolean,
  ) => {
    if (!viewportRef.current || !canvasRef.current) return

    // Compute bounding box from actual rendered DOM children
    const canvas = canvasRef.current
    let minX = Infinity, minY = Infinity, maxX = 0, maxY = 0
    for (const child of Array.from(canvas.children)) {
      const el = child as HTMLElement
      if (el.tagName === 'svg' || !el.offsetWidth || el.hasAttribute('data-overlay-canvas')) continue
      const x = el.offsetLeft
      const y = el.offsetTop
      const w = el.offsetWidth
      const h = el.offsetHeight
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x + w)
      maxY = Math.max(maxY, y + h)
    }
    if (minX === Infinity) return
    const vpW = viewportRef.current.clientWidth
    const vpH = viewportRef.current.clientHeight
    const insetTop = inset?.top ?? 0
    const insetBottom = inset?.bottom ?? 0
    const pad = 40
    const c = camera.current
    c.zoom = Math.min(vpW / (maxX - minX + pad * 2), (vpH - insetTop - insetBottom) / (maxY - minY + pad * 2), 1.5)
    c.x = (vpW - (maxX - minX) * c.zoom) / 2 - minX * c.zoom
    c.y = insetTop + ((vpH - insetTop - insetBottom) - (maxY - minY) * c.zoom) / 2 - minY * c.zoom

    if (animate) {
      const el = canvasRef.current
      el.style.transition = 'transform 600ms cubic-bezier(0.23, 0.88, 0.34, 0.99)'
      applyCamera()
      // Remove transition after animation to not interfere with pan/zoom
      const onEnd = () => { el.style.transition = ''; el.removeEventListener('transitionend', onEnd) }
      el.addEventListener('transitionend', onEnd)
    } else {
      applyCamera()
    }
  }, [viewportRef, canvasRef, applyCamera])

  // Returns a deselect callback; the caller provides its own selectedId setter
  const setup = useCallback((onDeselect: () => void) => {
    if (isSetup.current || !viewportRef.current) return
    isSetup.current = true
    const vp = viewportRef.current

    let dragMoved = false

    handlers.current.wheel = (e: WheelEvent) => {
      e.preventDefault()
      const c = camera.current
      if (e.ctrlKey || e.metaKey) {
        const delta = -Math.sign(e.deltaY) * Math.min(Math.abs(e.deltaY), 10)
        const factor = 1 + delta * 0.02
        const newZoom = Math.max(0.2, Math.min(4, c.zoom * factor))
        const rect = vp.getBoundingClientRect()
        const mx = e.clientX - rect.left
        const my = e.clientY - rect.top
        const wx = (mx - c.x) / c.zoom
        const wy = (my - c.y) / c.zoom
        c.x = mx - wx * newZoom
        c.y = my - wy * newZoom
        c.zoom = newZoom
      } else {
        c.x -= e.deltaX
        c.y -= e.deltaY
      }
      applyCamera()
    }
    vp.addEventListener('wheel', handlers.current.wheel, { passive: false })

    handlers.current.mousedown = (e: MouseEvent) => {
      if (e.target instanceof Element && e.target.closest('.zone-card, .entity-card, .agent-dot, .agent-name-label, .map-free-entity, [data-agent-id]')) return
      dragging.current = true
      dragMoved = false
      dragLast.current = { x: e.clientX, y: e.clientY }
      vp.style.cursor = 'grabbing'
      e.preventDefault()
    }
    vp.addEventListener('mousedown', handlers.current.mousedown)

    handlers.current.move = (e: MouseEvent) => {
      if (!dragging.current) return
      dragMoved = true
      const c = camera.current
      c.x += e.clientX - dragLast.current.x
      c.y += e.clientY - dragLast.current.y
      dragLast.current = { x: e.clientX, y: e.clientY }
      applyCamera()
    }
    handlers.current.up = () => {
      if (!dragging.current) return
      if (!dragMoved) onDeselect()
      dragging.current = false
      if (viewportRef.current) viewportRef.current.style.cursor = 'grab'
    }
    document.addEventListener('mousemove', handlers.current.move)
    document.addEventListener('mouseup', handlers.current.up)

    handlers.current.gStart = (e: Event) => e.preventDefault()
    handlers.current.gChange = (e: any) => {
      e.preventDefault()
      camera.current.zoom = Math.max(0.2, Math.min(4, camera.current.zoom * e.scale))
      applyCamera()
    }
    document.addEventListener('gesturestart', handlers.current.gStart)
    document.addEventListener('gesturechange', handlers.current.gChange)
  }, [viewportRef, applyCamera])

  const cleanup = useCallback(() => {
    if (!isSetup.current) return
    isSetup.current = false
    const vp = viewportRef.current
    const h = handlers.current
    if (vp) {
      if (h.wheel) vp.removeEventListener('wheel', h.wheel)
      if (h.mousedown) vp.removeEventListener('mousedown', h.mousedown)
    }
    if (h.move) document.removeEventListener('mousemove', h.move)
    if (h.up) document.removeEventListener('mouseup', h.up)
    if (h.gStart) document.removeEventListener('gesturestart', h.gStart)
    if (h.gChange) document.removeEventListener('gesturechange', h.gChange)
    handlers.current = { wheel: null, mousedown: null, move: null, up: null, gStart: null, gChange: null }
  }, [viewportRef])

  return { setup, cleanup, centerView, applyCamera }
}
