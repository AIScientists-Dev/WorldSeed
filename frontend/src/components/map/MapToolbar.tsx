/* WorldSeed — MapToolbar: top-right toolbar on the map viewport.
 *
 * Agent avatar row + map-level controls. Flex row, gap between items.
 * Auto-hides on cursor idle, appears on mouse move.
 * Hidden entirely in theater mode.
 */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PAPER_EASE } from '@/lib/motion'
import { AnimatePresence, motion } from 'motion/react'
import { useTheaterStore } from '@/stores/theater'
import { useWorldStore } from '@/stores/world'
import { useCursorIdle } from '@/hooks/useCursorIdle'
import { useMapSelection } from '@/components/MapSelectionContext'
import { agentColor } from '@/lib/detail-panel'
import { humanize } from '@/lib/helpers'
import { uiConfig } from '@/lib/ui-config'
import { FilmSlate } from '@phosphor-icons/react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
const MAX_VISIBLE_AVATARS = 6

function getInitials(id: string): string {
  // For CJK characters, return the first character
  if (/[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]/.test(id)) {
    return id.charAt(0)
  }
  return id.slice(0, 2).toUpperCase()
}

export default function MapToolbar() {
  const { t } = useTranslation()
  const theaterActive = useTheaterStore(s => s.active)
  const { visible } = useCursorIdle(3000)
  const entities = useWorldStore(s => s.entities)
  const { selectedId: mapSelectedId, setSelectedId: setMapSelectedId } = useMapSelection()

  const agents = useMemo(
    () => entities.filter(e => e.type === 'agent'),
    [entities],
  )

  const [showAll, setShowAll] = useState(false)

  if (theaterActive) return null

  const limit = showAll ? agents.length : MAX_VISIBLE_AVATARS
  const visibleAgents = agents.slice(0, limit)
  const overflowCount = agents.length - limit

  return (
    <div className="absolute right-3 top-3 z-40 pointer-events-none">
      <AnimatePresence>
        {visible && (
          <motion.div
            key="map-toolbar"
            className="flex items-center gap-2 pointer-events-auto"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: PAPER_EASE }}
          >
            <TooltipProvider delayDuration={150}>

              {/* ── Agent avatars ── */}
              {agents.length > 0 && (
                <>
                  <div className="flex items-center">
                    {visibleAgents.map((agent, i) => (
                      <AgentAvatar
                        key={agent.id}
                        agent={agent}
                        isFirst={i === 0}
                        isSelected={mapSelectedId === agent.id}
                        onSelect={() => setMapSelectedId(agent.id)}
                      />
                    ))}
                    {overflowCount > 0 && (
                      <button
                        onClick={() => setShowAll(true)}
                        className="flex items-center justify-center rounded-full bg-black/35 text-white/75 backdrop-blur-md border border-white/10 shadow-md text-[10px] font-medium select-none cursor-pointer hover:bg-black/50 hover:text-white transition-colors"
                        style={{
                          width: 34,
                          height: 34,
                          marginLeft: -8,
                          fontFamily: 'var(--font-data)',
                        }}
                      >
                        +{overflowCount}
                      </button>
                    )}
                  </div>

                  {/* Separator dot */}
                  <div
                    className="rounded-full shrink-0"
                    style={{
                      width: 3,
                      height: 3,
                      background: 'rgba(0,0,0,0.15)',
                    }}
                  />
                </>
              )}

              {/* ── Theater button ── */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => useTheaterStore.getState().enter()}
                    className="flex items-center justify-center rounded-full bg-black/35 text-white/75 backdrop-blur-md border border-white/10 shadow-md hover:bg-black/50 hover:text-white transition-colors cursor-pointer select-none"
                    style={{ width: 34, height: 34 }}
                  >
                    <FilmSlate size={18} />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs">{t('map.theaterMode')}</TooltipContent>
              </Tooltip>

            </TooltipProvider>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ── Agent avatar circle ── */

interface AgentAvatarProps {
  agent: any
  isFirst: boolean
  isSelected: boolean
  onSelect: () => void
}

function AgentAvatar({ agent, isFirst, isSelected, onSelect }: AgentAvatarProps) {
  const [imgError, setImgError] = useState(false)
  const avatarSrc = uiConfig.avatarUrl(agent)
  const showImage = avatarSrc && !imgError

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onSelect}
          className="rounded-full cursor-pointer select-none shrink-0 transition-shadow"
          style={{
            width: 34,
            height: 34,
            marginLeft: isFirst ? 0 : -8,
            background: agentColor(agent.id),
            border: isSelected
              ? '3px solid #fff'
              : '3px solid rgba(255,255,255,0.85)',
            boxShadow: isSelected
              ? '0 0 0 2px rgba(255,255,255,0.5), 0 0 0 1px rgba(0,0,0,0.1), 0 2px 8px rgba(0,0,0,0.3)'
              : '0 0 0 1px rgba(0,0,0,0.1), 0 2px 8px rgba(0,0,0,0.3)',
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
          }}
        >
          {showImage ? (
            <img
              alt={humanize(agent.id)}
              src={avatarSrc}
              onError={() => setImgError(true)}
              style={{
                width: '100%',
                height: '100%',
                borderRadius: '50%',
                objectFit: 'cover',
              }}
            />
          ) : (
            <span
              className="text-white font-semibold leading-none select-none"
              style={{ fontSize: 10 }}
            >
              {getInitials(agent.id)}
            </span>
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="text-xs">
        {humanize(agent.id)}
      </TooltipContent>
    </Tooltip>
  )
}
