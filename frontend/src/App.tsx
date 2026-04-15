import { Outlet } from 'react-router-dom'
import { useRouteGuards } from '@/router/guards'
import SettingsModal from '@/components/modals/SettingsModal'
import { Toaster } from '@/components/ui/sonner'
import { useUIStore } from '@/stores/ui'

export default function App() {
  useRouteGuards()
  const showSettings = useUIStore(s => s.showSettings)

  return (
    <>
      <Outlet />
      {showSettings && <SettingsModal />}
      <Toaster position="top-center" />
    </>
  )
}
