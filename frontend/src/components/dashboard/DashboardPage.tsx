import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { useUIStore } from '@/stores/ui'
import { useDashboardSetup } from '@/hooks/useDashboardSetup'
import { useDemoAmbient } from '@/lib/demo'
import HeaderBar from '@/components/layout/HeaderBar'
import StreamPanel from '@/components/stream/StreamPanel'
import ChronicleBar from '@/components/stream/ChronicleBar'
import ChronicleSheet from '@/components/stream/ChronicleSheet'
import GmView from '@/components/gm/GmView'
import MapDetailPanel from '@/components/map/MapDetailPanel'
import { MapSelectionContext } from '@/components/MapSelectionContext'

export default function DashboardPage({ header }: { header?: ReactNode } = {}) {
  useDemoAmbient()
  const {
    entities,
    mapSelectedId,
    setMapSelectedId,
    rightPanelRef,
    startResizeRight,
  } = useDashboardSetup()

  const rightTab = useUIStore(s => s.rightTab)

  const isMapDetailVisible = mapSelectedId &&
    entities.find(e => e.id === mapSelectedId)

  return (
    <MapSelectionContext.Provider value={{ selectedId: mapSelectedId, setSelectedId: setMapSelectedId }}>
      <div className="flex h-screen flex-col overflow-hidden">
        {header ?? <HeaderBar />}
        <ChronicleBar />
        <div className="layout">
          <div className="content">
            <div className="content-main">
              <Outlet />
            </div>
            <div className="resize-handle-v" onMouseDown={startResizeRight}></div>
            <div className="content-right" ref={rightPanelRef}>
              {isMapDetailVisible ? (
                <MapDetailPanel
                  selectedId={mapSelectedId}
                  onSelect={(id) => setMapSelectedId(id)}
                  onDeselect={() => setMapSelectedId(null)}
                />
              ) : (
                <div className="panel">
                  {rightTab === 'stream' ? <StreamPanel /> : <GmView />}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      <ChronicleSheet />
    </MapSelectionContext.Provider>
  )
}
