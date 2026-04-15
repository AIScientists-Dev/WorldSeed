/* WorldSeed — AgentRow: single agent in a zone's bottom row.
 *
 * Pure display: avatar + name. No overlay rendering.
 * Bubbles are rendered by OverlayCanvas (separate layer, pre-computed positions).
 * Uses layoutId for cross-zone movement animation.
 * State effects are entity-only (not applied to agents).
 */

import { motion } from 'motion/react'
import { uiConfig } from '@/lib/ui-config'
import { agentColor, getShowValue } from '@/lib/detail-panel'
import { humanize } from '@/lib/helpers'
import { PAPER_EASE } from '@/lib/motion'

interface Props {
  agent: any
  onSelect: (id: string) => void
}

export default function AgentRow({ agent, onSelect }: Props) {
  const bind = uiConfig.getBind(agent)
  const showValue = getShowValue(agent, bind)
  const avatarSrc = uiConfig.avatarUrl(agent)

  return (
    <motion.div
      layoutId={`agent-${agent.id}`}
      className="relative flex flex-col items-center gap-0.5 min-w-0 cursor-pointer"
      data-agent-id={agent.id}
      onClick={(e) => { e.stopPropagation(); onSelect(agent.id) }}
      transition={{ layout: { duration: 0.5, ease: PAPER_EASE } }}
    >
      {/* Avatar */}
      <div className="agent-dot shrink-0" style={{ background: agentColor(agent.id) }}>
        <span className="agent-dot-initial">
          {agent.id.charAt(0) || '?'}
        </span>
        {avatarSrc && (
          <img alt={humanize(agent.id)} className="agent-dot-avatar" src={avatarSrc}
            onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none' }} />
        )}
      </div>

      {/* Name + optional show value */}
      <span className="agent-name-label max-w-[72px] truncate block">
        {humanize(agent.id)}
      </span>
      {showValue != null && (
        <span className="agent-show-value">
          {String(showValue)}
        </span>
      )}
    </motion.div>
  )
}
