/* WorldSeed — Panel resize hook */

export function usePanelResize() {
  function makeDragHandler(
    getPanel: () => HTMLElement | null,
    axis: 'x' | 'y',
    storageKey: string,
    minPx: number,
    maxFrac: number,
  ) {
    return function (e: React.MouseEvent) {
      e.preventDefault()
      const panel = getPanel()
      if (!panel) return
      const startPos = axis === 'y' ? e.clientY : e.clientX
      const startSize = axis === 'y' ? panel.offsetHeight : panel.offsetWidth
      const handle = e.target as HTMLElement
      handle.classList.add('dragging')

      function onMove(ev: MouseEvent) {
        const pos = axis === 'y' ? ev.clientY : ev.clientX
        const ref = document.documentElement
        const maxPx = axis === 'y' ? (ref.offsetHeight || window.innerHeight) : (ref.offsetWidth || window.innerWidth)
        const size = Math.max(minPx, Math.min(maxPx * maxFrac, startSize + startPos - pos))
        if (axis === 'x') panel.style.flex = 'none'
        panel.style[axis === 'y' ? 'height' : 'width'] = size + 'px'
      }

      function onUp() {
        handle.classList.remove('dragging')
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        localStorage.setItem(storageKey, panel.style[axis === 'y' ? 'height' : 'width'])
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    }
  }

  return { makeDragHandler }
}
