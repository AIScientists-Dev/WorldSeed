/* WorldSeed — Scroll-navigated panel wrapper.
 *
 * Wraps react-scroll-to-bottom for instant auto-scroll (sticky) and
 * bidirectional scroll buttons: ↑ when not at top, ↓ when not at bottom.
 * Library's built-in follow button is hidden; we render our own.
 */
import { useEffect } from 'react'
import ScrollToBottom, { useAtTop, useScrollToBottom, useScrollToTop, useSticky } from 'react-scroll-to-bottom'
import { ArrowUp, ArrowDown } from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'

interface Props {
  children: React.ReactNode
  /** Value that triggers scroll-to-bottom when it changes */
  dep: unknown
  className?: string
  scrollViewClassName?: string
}

function ScrollNav({ children, dep }: { children: React.ReactNode; dep: unknown }) {
  const scrollToBottom = useScrollToBottom()
  const scrollToTop = useScrollToTop()
  const [sticky] = useSticky()
  const [atTop] = useAtTop()

  useEffect(() => {
    if (sticky) scrollToBottom({ behavior: 'smooth' })
  }, [dep, sticky, scrollToBottom])

  return (
    <>
      {children}
      {(!atTop || !sticky) && (
        <div className="sticky bottom-2 z-10 ml-auto flex w-0 -translate-x-3 flex-col gap-1 items-end pointer-events-none">
          {!atTop && (
            <Button
              variant="outline"
              size="icon-sm"
              className="rounded-full shadow-sm pointer-events-auto"
              onClick={() => scrollToTop({ behavior: 'smooth' })}
              aria-label="Scroll to top"
            >
              <ArrowUp size={14} />
            </Button>
          )}
          {!sticky && (
            <Button
              variant="outline"
              size="icon-sm"
              className="rounded-full shadow-sm pointer-events-auto"
              onClick={() => scrollToBottom({ behavior: 'smooth' })}
              aria-label="Scroll to bottom"
            >
              <ArrowDown size={14} />
            </Button>
          )}
        </div>
      )}
    </>
  )
}

export function AutoScrollPanel({ children, dep, className, scrollViewClassName }: Props) {
  return (
    <ScrollToBottom
      className={className}
      scrollViewClassName={scrollViewClassName}
      initialScrollBehavior="auto"
      followButtonClassName="scroll-to-bottom-btn-hidden"
    >
      <ScrollNav dep={dep}>{children}</ScrollNav>
    </ScrollToBottom>
  )
}
