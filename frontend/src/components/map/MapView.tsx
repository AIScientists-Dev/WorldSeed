/* WorldSeed — MapView: collage-style world map with pan/zoom.
 *
 * Renders zone cards on a 4000×3000 canvas with camera controls.
 * Delegates zone rendering to ZoneCard, overlays to NarrativeBar.
 *
 * Component hierarchy:
 *   MapView (canvas + camera)
 *     ZoneCard (zone bg + items + agents)
 *       EntityCard (item card — shared component)
 *       AgentRow (avatar + name + action chip)
 *     EntityRenderer (free entities — dispatches by scene type)
 *       AgentRow | EntityCard | fallback pill
 *     NarrativeBar viewport layer (speech bubbles, narrative bars)
 */

import { useRef, useState, useMemo, useEffect } from 'react'
import { AnimatePresence, LayoutGroup } from 'motion/react'
import { useWorldStore } from '@/stores/world'
import { useTheaterStore } from '@/stores/theater'
import { useEntities } from '@/hooks/useWorldState'
import { useMapCamera } from '@/hooks/useMapCamera'
import { useMapSelection } from '@/components/MapSelectionContext'
import { uiConfig } from '@/lib/ui-config'
import { useSubtitlePlayer } from '@/hooks/useSubtitlePlayer'
import { computeMapData, collageStyle, freeStyle, getMaxZoneBottom, computeConnections } from '@/lib/map-layout'
import { flash } from '@/lib/motion'
import ZoneCard from './ZoneCard'

import EntityRenderer from './EntityRenderer'
import MapToolbar from './MapToolbar'
import OverlayCanvas from './OverlayCanvas'
import NarrativeBar from './overlays/NarrativeBar'
import GmPill from './GmPill'
import TheaterChrome from './TheaterChrome'
import TheaterOverlay from './TheaterOverlay'

export default function MapView() {
  const entities = useEntities()
  const scene = useWorldStore(s => s.scene)
  const events = useWorldStore(s => s.events)

  const viewportRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const camera = useMapCamera(viewportRef, canvasRef)
  const { selectedId: mapSelectedId, setSelectedId: setMapSelectedId } = useMapSelection()
  const [connections, setConnections] = useState<{ x1: number; y1: number; x2: number; y2: number }[]>([])

  const theaterActive = useTheaterStore(s => s.active)
  const prevEventsLen = useRef(0)
  // Single subtitle player instance — shared by OverlayCanvas + NarrativeBar
  const { cueFinished, scheduleChipAdvance, speed: subtitleSpeed, paused: subtitlePaused } = useSubtitlePlayer()

  const mapData = useMemo(() => computeMapData(entities), [entities])

  function mapSelect(id: string) {
    setMapSelectedId(mapSelectedId === id ? null : id)
  }

  function getCollageStyle(entityId: string) {
    const idx = mapData.zones.findIndex(z => z.entity.id === entityId)
    return collageStyle(entityId, uiConfig.layout, idx)
  }

  function updateConnections() {
    setConnections(computeConnections(mapData.zones, uiConfig.layout))
  }

  // Setup camera when entities arrive (or run switches)
  // useMapCamera.setup() is internally idempotent via isSetup ref.
  // cleanup resets that ref, so next setup() call re-attaches handlers.
  useEffect(() => {
    if (!entities.length || !uiConfig.loaded) return
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        camera.setup(() => setMapSelectedId(null))
        camera.centerView(uiConfig.layout, { bottom: 100 })
        updateConnections()
      })
    })
    return () => { camera.cleanup() }
  }, [entities.length, scene]) // eslint-disable-line react-hooks/exhaustive-deps

  // Entities change → update connections
  useEffect(() => {
    if (uiConfig.loaded) updateConnections()
  }, [entities.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Theater mode → recenter after viewport goes fullscreen / returns
  useEffect(() => {
    if (!entities.length || !uiConfig.loaded) return
    const inset = theaterActive ? { top: 48, bottom: 100 } : { bottom: 100 }
    // position:fixed applies instantly, rAF ensures browser has new dimensions
    requestAnimationFrame(() => {
      camera.centerView(uiConfig.layout, inset, true)
    })
  }, [theaterActive]) // eslint-disable-line react-hooks/exhaustive-deps

  // Flash agent dots + animate entity cards on new events
  useEffect(() => {
    const newLen = events.length
    if (newLen > prevEventsLen.current) {
      const newEvents = events.slice(prevEventsLen.current)
      for (const ev of newEvents) {
        // Agent dot flash (only for events with a source agent)
        if (ev.source) {
          const agentEl = document.querySelector(`[data-agent-id="${ev.source}"] .agent-dot`)
          if (agentEl) flash(agentEl)
        }
        // Entity card event animation — works even without source/target
        const effect = uiConfig.getEventEffect(ev.type || '')
        if (effect) {
          const targetId = ev.target || ev.source
          if (targetId) {
            const entityEl = document.querySelector(`[data-entity-id="${targetId}"]`)
            if (entityEl) {
              const cls = `entity-anim-${effect}`
              entityEl.classList.remove(cls)
              void (entityEl as HTMLElement).offsetWidth // force reflow
              entityEl.classList.add(cls)
              entityEl.addEventListener('animationend', () => entityEl.classList.remove(cls), { once: true })
            }
          }
        }
      }
    }
    prevEventsLen.current = newLen
  }, [events.length]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={`map-viewport paper-bg${theaterActive ? ' theater-fullscreen' : ''}`} ref={viewportRef}>
      <div className="map-canvas" ref={canvasRef}>
        {/* LayoutGroup enables cross-zone agent movement animation (covers zones + free) */}
        <LayoutGroup>
        {/* Zone cards */}
        {mapData.zones.map(zone => (
          <ZoneCard
            key={zone.entity.id}
            zone={zone}
            agents={mapData.agents[zone.entity.id] || []}
            items={mapData.items[zone.entity.id] || []}
            selected={mapSelectedId === zone.entity.id}
            style={getCollageStyle(zone.entity.id)}
            onSelect={mapSelect}
          />
        ))}

        {/* Free entities — rendered by scene type via EntityRenderer */}
        {mapData.free.map((ent: any, idx: number) => (
          <EntityRenderer
            key={ent.id}
            entity={ent}
            onSelect={mapSelect}
            selected={mapSelectedId === ent.id}
            style={{ position: 'absolute', ...freeStyle(idx, getMaxZoneBottom(uiConfig.layout)) }}
          />
        ))}
        </LayoutGroup>

        {/* Overlay bubbles — positioned by pure math, above zones */}
        <OverlayCanvas onChipReady={scheduleChipAdvance} onSpeechDone={cueFinished} speed={subtitleSpeed} paused={subtitlePaused} />

        {/* Connection lines */}
        <svg className="absolute inset-0 z-[2] w-[4000px] h-[3000px] pointer-events-none">
          {connections.map((c, i) => {
            const dx = c.x2 - c.x1
            const dy = c.y2 - c.y1
            const dist = Math.sqrt(dx * dx + dy * dy)
            if (dist === 0) {
              return <line key={i} x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2}
                          stroke="#c4b5a0" strokeOpacity="0.35" strokeWidth="1.5"
                          strokeLinecap="round" />
            }
            const mx = (c.x1 + c.x2) / 2
            const my = (c.y1 + c.y2) / 2
            const offset = dist * 0.12
            const sign = i % 2 === 0 ? 1 : -1
            const cx = mx + (-dy / dist) * offset * sign
            const cy = my + (dx / dist) * offset * sign
            return (
              <path key={i}
                    d={`M ${c.x1} ${c.y1} Q ${cx} ${cy} ${c.x2} ${c.y2}`}
                    fill="none"
                    stroke="#c4b5a0" strokeOpacity="0.35" strokeWidth="1.5"
                    strokeLinecap="round" />
            )
          })}
        </svg>
      </div>

      <MapToolbar />
      <NarrativeBar onDone={cueFinished} speed={subtitleSpeed} paused={subtitlePaused} />
      <GmPill />
      <TheaterChrome />

      {/* Theater backdrop (portal to body, dims dashboard beneath) */}
      <AnimatePresence>
        {theaterActive && <TheaterOverlay key="theater-overlay" />}
      </AnimatePresence>
    </div>
  )
}
