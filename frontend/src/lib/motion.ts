/* WorldSeed — Motion Runtime: shared easing + animation utilities */

/** Paper easing curve — used across all WorldSeed animations. */
export const PAPER_EASE = [0.23, 0.88, 0.34, 0.99] as const

/** One-shot opacity flash on an element (Web Animations API). */
export function flash(el: Element): void {
  if (!el || !('animate' in el)) return
  ;(el as HTMLElement).animate(
    [{ opacity: 0.4 }, { opacity: 1 }],
    { duration: 200, easing: 'ease-out' }
  )
}
