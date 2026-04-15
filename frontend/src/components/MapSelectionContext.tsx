import { createContext, useContext } from 'react'

interface MapSelectionContextType {
  selectedId: string | null
  setSelectedId: (id: string | null) => void
}

export const MapSelectionContext = createContext<MapSelectionContextType>({
  selectedId: null,
  setSelectedId: () => {},
})

export function useMapSelection() {
  return useContext(MapSelectionContext)
}
