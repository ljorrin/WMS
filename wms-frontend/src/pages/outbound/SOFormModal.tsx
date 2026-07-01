import { useState } from 'react'
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { outboundApi, masterApi, warehouseApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Combobox } from '@/components/ui/Combobox'
import type { Product } from '@/types'
import toast from 'react-hot-toast'

interface SOLineDraft {
  key: string
  product_id: string
  product_label: string
  quantity_ordered: string
  unit_price: string
}

const emptyLine = (): SOLineDraft => ({
  key: crypto.randomUUID(),
  product_id: '',
  product_label: '',
  quantity_ordered: '',
  unit_price: '',
})

const CURRENCIES = ['USD', 'PAB']
const INCOTERMS = ['EXW', 'FCA', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP', 'FAS', 'FOB', 'CFR', 'CIF']

interface Props {
  open: boolean
  onClose: () => void
}

export function SOFormModal({ open, onClose }: Props) {
  const qc = useQueryClient()

  const [customerId, setCustomerId] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [warehouseLabel, setWarehouseLabel] = useState('')
  const [priority, setPriority] = useState('5')
  const [currency, setCurrency] = useState('USD')
  const [deliveryDate, setDeliveryDate] = useState('')
  const [incoterms, setIncoterms] = useState('')
  const [notes, setNotes] = useState('')
  const [lines, setLines] = useState<SOLineDraft[]>([emptyLine()])

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
    enabled: open,
  })

  const reset = () => {
    setCustomerId(''); setWarehouseId(''); setWarehouseLabel('')
    setPriority('5'); setCurrency('USD'); setDeliveryDate('')
    setIncoterms(''); setNotes(''); setLines([emptyLine()])
  }

  const updateLine = (key: string, patch: Partial<SOLineDraft>) =>
    setLines(ls => ls.map(l => l.key === key ? { ...l, ...patch } : l))

  const validLines = lines.filter(
    l => l.product_id && Number(l.quantity_ordered) > 0 && Number(l.unit_price) >= 0
  )

  const canSubmit = customerId.length >= 3 && warehouseId &&
    validLines.length > 0

  const createMut = useMutation({
    mutationFn: () => outboundApi.createSO({
      customer_id: customerId,
      warehouse_id: warehouseId,
      priority: Number(priority),
      currency,
      requested_delivery_date: deliveryDate || undefined,
      incoterms: incoterms || undefined,
      notes: notes || undefined,
      lines: validLines.map(l => ({
        product_id: l.product_id,
        quantity_ordered: Number(l.quantity_ordered),
        unit_price: Number(l.unit_price),
      })),
    }),
    onSuccess: () => {
      toast.success('Orden de venta creada')
      qc.invalidateQueries({ queryKey: ['sos'] })
      reset(); onClose()
    },
    onError: () => toast.error('No se pudo crear la orden de venta'),
  })

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose() }}
      title="Nueva Orden de Venta"
      description="Crea una SO en borrador. Después de crearla, confírmala para reservar stock."
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={() => { reset(); onClose() }}>Cancelar</Button>
          <Button size="sm" disabled={!canSubmit} loading={createMut.isPending}
            onClick={() => createMut.mutate()}>
            Crear SO
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input
            label="Customer ID"
            value={customerId}
            onChange={e => setCustomerId(e.target.value)}
            placeholder="UUID o código del cliente"
          />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Bodega</label>
            <select
              value={warehouseId}
              onChange={e => {
                setWarehouseId(e.target.value)
                const w = warehouses?.items.find(x => x.id === e.target.value)
                setWarehouseLabel(w ? `${w.code} — ${w.name}` : '')
              }}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
            >
              <option value="">Seleccionar…</option>
              {warehouses?.items.map(w => (
                <option key={w.id} value={w.id}>{w.code} — {w.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Prioridad</label>
            <select value={priority} onChange={e => setPriority(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              {Array.from({ length: 10 }, (_, i) => i + 1).map(p => (
                <option key={p} value={p}>{p}{p === 1 ? ' (urgente)' : p === 10 ? ' (mínima)' : ''}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Moneda</label>
            <select value={currency} onChange={e => setCurrency(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Incoterms</label>
            <select value={incoterms} onChange={e => setIncoterms(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              <option value="">Sin incoterms</option>
              {INCOTERMS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Fecha de entrega solicitada</label>
          <input
            type="date"
            value={deliveryDate}
            onChange={e => setDeliveryDate(e.target.value)}
            className="h-9 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm"
          />
        </div>

        {/* Líneas */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-semibold text-gray-800">Líneas de producto</label>
            <Button variant="ghost" size="sm" onClick={() => setLines(ls => [...ls, emptyLine()])}>
              <Plus className="h-4 w-4" /> Agregar línea
            </Button>
          </div>
          <div className="space-y-2">
            {lines.map((line, idx) => (
              <div key={line.key} className="rounded-lg border border-gray-100 bg-gray-50/50 p-3">
                <div className="grid grid-cols-12 items-end gap-2">
                  <div className="col-span-5">
                    <Combobox<Product>
                      placeholder="Buscar producto…"
                      value={line.product_id}
                      displayLabel={line.product_label}
                      queryKey={`products-so-line-${idx}`}
                      fetcher={s => masterApi.getProducts({ search: s, page_size: 20, status: 'active' })}
                      getKey={p => p.id}
                      getLabel={p => `${p.sku} — ${p.name}`}
                      onSelect={p => updateLine(line.key, { product_id: p.id, product_label: `${p.sku} — ${p.name}` })}
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="Cantidad"
                      value={line.quantity_ordered}
                      onChange={e => updateLine(line.key, { quantity_ordered: e.target.value })}
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="Precio unit."
                      value={line.unit_price}
                      onChange={e => updateLine(line.key, { unit_price: e.target.value })}
                    />
                  </div>
                  <div className="col-span-1 flex justify-center pb-1">
                    {lines.length > 1 && (
                      <button
                        onClick={() => setLines(ls => ls.filter(l => l.key !== line.key))}
                        className="text-red-500 hover:text-red-700"
                        title="Eliminar línea"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <Input
          label="Notas (opcional)"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Instrucciones especiales de entrega"
        />
      </div>
    </Modal>
  )
}
