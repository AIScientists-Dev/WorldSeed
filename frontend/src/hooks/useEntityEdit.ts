/* WorldSeed — Entity inline edit hook */
import { apiPost } from '@/lib/api'
import { formatVal } from '@/lib/helpers'
import { SAVED_PROP_TIMEOUT_MS } from '@/lib/constants'
import { useUIStore } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'

export function useEntityEdit() {
  function startEditProperty(entityId: string, key: string, value: any) {
    useUIStore.setState({
      editingProp: { entity: entityId, key, value: formatVal(value) },
    })
    requestAnimationFrame(() => {
      const inputs = document.querySelectorAll('.prop-edit-input')
      if (inputs.length) (inputs[inputs.length - 1] as HTMLElement).focus()
    })
  }

  function cancelEditProperty() {
    useUIStore.setState({
      editingProp: { entity: null, key: null, value: '' },
    })
  }

  async function saveProperty(entityId: string, key: string) {
    const ui = useUIStore.getState()
    if (ui.editingProp.entity !== entityId || ui.editingProp.key !== key) return
    const raw = ui.editingProp.value

    let parsed: any
    if (raw === 'true') parsed = true
    else if (raw === 'false') parsed = false
    else if (raw === 'null') parsed = null
    else if (!isNaN(Number(raw)) && raw.trim() !== '') parsed = Number(raw)
    else { try { parsed = JSON.parse(raw) } catch { parsed = raw } }

    const ws = useWorldStore.getState()
    const ent = ws.entities.find((e: any) => e.id === entityId)
    const oldVal = ent ? (ent.properties ? ent.properties[key] : (ent as any)[key]) : undefined
    if (JSON.stringify(parsed) === JSON.stringify(oldVal)) {
      cancelEditProperty()
      return
    }

    cancelEditProperty()

    const result = await apiPost('/api/entity/set', {
      entity_id: entityId, property: key, value: parsed,
    })

    if (result.ok) {
      useUIStore.setState({
        savedProp: { entity: entityId, key, ts: Date.now() },
      })
      setTimeout(() => {
        const current = useUIStore.getState().savedProp
        if (current.entity === entityId && current.key === key) {
          useUIStore.setState({ savedProp: { entity: null, key: null, ts: 0 } })
        }
      }, SAVED_PROP_TIMEOUT_MS)
    }
  }

  return { startEditProperty, cancelEditProperty, saveProperty }
}
