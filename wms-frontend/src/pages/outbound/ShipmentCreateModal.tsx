import { useState } from 'react'
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { outboundApi, warehouseApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Combobox } from '@/components/ui/Combobox'
import type { SalesOrder } from '@/types'
import toast from 'react-hot-toast'

const CARRIER_TYPES = [
  { value: 'ground', label: 'Terrestre' },
  { value: 'air', label: 'Aéreo' },
  { value: 'sea', label: 'Marítimo' },
  { value: 'courier', label: 'Mensajería' },
]

interface Props {
  open: boolean
  onClose: () => void
}

// Fecha local en formato datetime-local
const nowLocal = () => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

export function ShipmentCreateModal({ open, onClose }: Props) {
  const qc = useQueryClient()

  const [soId, setSoId] = useState('')
  const [soLabel, setSoLabel] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [carrierType, setCarrierType] = useState('ground')
  const [carrierName, setCarrierName] = useState('')
  const [scheduledPickup, setScheduledPickup] = useState(nowLocal())
  const [estimatedDelivery, setEstimatedDelivery] = useState('')
  const [isExport, setIsExport] = useState(false)
  const [notes, setNotes] = useState('')

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
    enabled: open,
  })

  const reset = () => {
    setSoId(''); setSoLabel(''); setWarehouseId('')
    setCarrierType('ground'); setCarrierName('')
    setScheduledPickup(nowLocal()); setEstimatedDelivery('')
    setIsExport(false); setNotes('')
  }

  const canSubmit = soId && warehouseId && scheduledPickup

  const createMut = useMutation({
    mutationFn: () => outboundApi.createShipment({
      so_id: soId,
      warehouse_id: warehouseId,
      carrier_type: carrierType,
      carrier_name: carrierName || undefined,
      scheduled_pickup: new Date(scheduledPickup).toISOString(),
      estimated_delivery: estimatedDelivery
        ? new Date(estimatedDelivery).toISOString()
        : undefined,
      is_export: isExport,
      notes: notes || undefined,
    }),
    onSuccess: () => {
      toast.success('Envío creado — pendiente de despacho')
      qc.invalidateQueries({ queryKey: ['shipments'] })
      reset(); onClose()
    },
    onError: () => toast.error('No se pudo crear el envío'),
  })

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose() }}
      title="Nuevo Envío"
      description="Registra un envío para una orden de venta empacada."
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={() => { reset(); onClose() }}>Cancelar</Button>
          <Button size="sm" disabled={!canSubmit} loading={createMut.isPending}
            onClick={() => createMut.mutate()}>
            Crear envío
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Combobox<SalesOrder>
            label="Orden de Venta"
            placeholder="Buscar SO empacada…"
            value={soId}
            displayLabel={soLabel}
            queryKey="sos-packed"
            fetcher={async s => {
              const res = await outboundApi.getSOs({ search: s, page_size: 20, status: 'packed' })
              return { items: res.items }
            }}
            getKey={so => so.id}
            getLabel={so => `${so.so_number} · ${so.customer_id}`}
            onSelect={so => {
              setSoId(so.id)
              setSoLabel(so.so_number)
              setWarehouseId(so.warehouse_id)
            }}
          />

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Bodega</label>
            <select
              value={warehouseId}
              onChange={e => setWarehouseId(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
            >
              <option value="">Seleccionar…</option>
              {warehouses?.items.map(w => (
                <option key={w.id} value={w.id}>{w.code} — {w.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Tipo de transportista</label>
            <select value={carrierType} onChange={e => setCarrierType(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              {CARRIER_TYPES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <Input
            label="Nombre del transportista"
            value={carrierName}
            onChange={e => setCarrierName(e.target.value)}
            placeholder="Ej: DHL, FedEx, Transportes XYZ…"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Recogida programada</label>
            <input
              type="datetime-local"
              value={scheduledPickup}
              onChange={e => setScheduledPickup(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Entrega estimada (opcional)</label>
            <input
              type="datetime-local"
              value={estimatedDelivery}
              onChange={e => setEstimatedDelivery(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="is-export"
            className="rounded"
            checked={isExport}
            onChange={e => setIsExport(e.target.checked)}
          />
          <label htmlFor="is-export" className="text-sm text-gray-700">
            Exportación internacional (requiere documentos aduaneros)
          </label>
        </div>

        <Input
          label="Notas (opcional)"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Instrucciones para el transportista"
        />
      </div>
    </Modal>
  )
}
