import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { inboundApi, masterApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Combobox } from '@/components/ui/Combobox'
import type { PurchaseOrder, LocationLite } from '@/types'
import toast from 'react-hot-toast'

interface GRNLineDraft {
  key: string
  product_id: string
  location_id: string
  location_label: string
  quantity_received: string
  quantity_rejected: string
  batch_number: string
  expiry_date: string
}

const RECEIVING_MODES = [
  { value: 'standard', label: 'Estándar' },
  { value: 'container', label: 'Contenedor' },
  { value: 'cross_dock', label: 'Cross-dock' },
]

const RECEIVABLE_STATUSES = ['confirmed', 'partially_received']

export function GRNFormModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [poId, setPoId] = useState('')
  const [poLabel, setPoLabel] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [receivingMode, setReceivingMode] = useState('standard')
  const [ambientTemp, setAmbientTemp] = useState('')
  const [productTemp, setProductTemp] = useState('')
  const [lines, setLines] = useState<GRNLineDraft[]>([])

  // Detalle de la OC seleccionada → precarga de líneas pendientes
  const { data: po } = useQuery({
    queryKey: ['po', poId, 'for-grn'],
    queryFn: () => inboundApi.getPO(poId),
    enabled: !!poId,
  })

  useEffect(() => {
    if (!po) return
    setWarehouseId(po.warehouse_id)
    setLines(
      (po.lines ?? [])
        .filter(l => Number(l.quantity_pending) > 0)
        .map(l => ({
          key: l.id,
          product_id: l.product_id,
          location_id: '',
          location_label: '',
          quantity_received: String(l.quantity_pending),
          quantity_rejected: '0',
          batch_number: '',
          expiry_date: '',
        })),
    )
  }, [po])

  const reset = () => {
    setPoId(''); setPoLabel(''); setWarehouseId(''); setReceivingMode('standard')
    setAmbientTemp(''); setProductTemp(''); setLines([])
  }

  const updateLine = (key: string, patch: Partial<GRNLineDraft>) =>
    setLines(ls => ls.map(l => (l.key === key ? { ...l, ...patch } : l)))

  const validLines = lines.filter(
    l => l.location_id && Number(l.quantity_received) > 0,
  )
  const canSubmit = poId && warehouseId && validLines.length > 0

  const createMut = useMutation({
    mutationFn: () => inboundApi.createGRN({
      warehouse_id: warehouseId,
      po_id: poId,
      receiving_mode: receivingMode,
      ambient_temp_celsius: ambientTemp ? Number(ambientTemp) : undefined,
      product_temp_celsius: productTemp ? Number(productTemp) : undefined,
      lines: validLines.map(l => ({
        product_id: l.product_id,
        location_id: l.location_id,
        quantity_received: Number(l.quantity_received),
        quantity_rejected: l.quantity_rejected ? Number(l.quantity_rejected) : 0,
        batch_number: l.batch_number || undefined,
        expiry_date: l.expiry_date || undefined,
      })),
    }),
    onSuccess: () => {
      toast.success('Recepción registrada (GRN en progreso)')
      qc.invalidateQueries({ queryKey: ['grns'] })
      qc.invalidateQueries({ queryKey: ['pos'] })
      reset(); onClose()
    },
    onError: () => toast.error('No se pudo registrar la recepción'),
  })

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose() }}
      title="Nueva Recepción (GRN)"
      description="Recibe mercancía contra una orden de compra confirmada."
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={() => { reset(); onClose() }}>Cancelar</Button>
          <Button size="sm" loading={createMut.isPending} disabled={!canSubmit}
            onClick={() => createMut.mutate()}>
            Registrar recepción
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Combobox<PurchaseOrder>
            label="Orden de compra"
            placeholder="Buscar por número de OC…"
            value={poId}
            displayLabel={poLabel}
            queryKey="pos-receivable"
            fetcher={async s => {
              const res = await inboundApi.getPOs({ search: s, page_size: 20 })
              return { items: res.items.filter(p => RECEIVABLE_STATUSES.includes(p.status)) }
            }}
            getKey={p => p.id}
            getLabel={p => `${p.po_number} · ${p.status}`}
            onSelect={p => { setPoId(p.id); setPoLabel(p.po_number) }}
          />
          <Select
            label="Modo de recepción"
            value={receivingMode}
            onChange={e => setReceivingMode(e.target.value)}
            options={RECEIVING_MODES}
          />
          <Input label="Temp. ambiente (°C)" type="number" step="0.1" value={ambientTemp}
            onChange={e => setAmbientTemp(e.target.value)} placeholder="Opcional" />
          <Input label="Temp. producto (°C)" type="number" step="0.1" value={productTemp}
            onChange={e => setProductTemp(e.target.value)} placeholder="Opcional (cadena de frío)" />
        </div>

        {!poId ? (
          <p className="rounded-lg border border-dashed border-gray-200 px-3 py-6 text-center text-sm text-gray-400">
            Selecciona una orden de compra para cargar sus líneas pendientes.
          </p>
        ) : lines.length === 0 ? (
          <p className="rounded-lg border border-dashed border-amber-200 bg-amber-50 px-3 py-4 text-center text-sm text-amber-700">
            Esta orden no tiene cantidades pendientes por recibir.
          </p>
        ) : (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-800">Líneas a recibir</h3>
            {lines.map(line => (
              <div key={line.key} className="rounded-lg border border-gray-100 bg-gray-50/50 p-3 space-y-2">
                <p className="font-mono text-xs text-gray-500">SKU: {line.product_id}</p>
                <div className="grid grid-cols-12 items-end gap-2">
                  <div className="col-span-5">
                    <Combobox<LocationLite>
                      placeholder="Ubicación staging…"
                      value={line.location_id}
                      displayLabel={line.location_label}
                      queryKey={`locations-${warehouseId}`}
                      fetcher={s => masterApi.getLocations({
                        search: s, warehouse_id: warehouseId, page_size: 20, status: 'active',
                      })}
                      getKey={x => x.id}
                      getLabel={x => x.code}
                      onSelect={x => updateLine(line.key, { location_id: x.id, location_label: x.code })}
                    />
                  </div>
                  <div className="col-span-2">
                    <Input placeholder="Recibido" type="number" min="0" step="0.01"
                      value={line.quantity_received}
                      onChange={e => updateLine(line.key, { quantity_received: e.target.value })} />
                  </div>
                  <div className="col-span-2">
                    <Input placeholder="Rechazado" type="number" min="0" step="0.01"
                      value={line.quantity_rejected}
                      onChange={e => updateLine(line.key, { quantity_rejected: e.target.value })} />
                  </div>
                  <div className="col-span-3">
                    <Input placeholder="Lote" value={line.batch_number}
                      onChange={e => updateLine(line.key, { batch_number: e.target.value })} />
                  </div>
                </div>
                <Input label="Vencimiento" type="date" value={line.expiry_date}
                  onChange={e => updateLine(line.key, { expiry_date: e.target.value })} className="max-w-[200px]" />
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
