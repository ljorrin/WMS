import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { inboundApi, masterApi, warehouseApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Combobox } from '@/components/ui/Combobox'
import { fmt } from '@/utils/format'
import type { Product, Supplier } from '@/types'
import toast from 'react-hot-toast'

interface LineDraft {
  key: string
  product_id: string
  product_label: string
  uom: string
  quantity_ordered: string
  unit_cost: string
}

const today = () => new Date().toISOString().slice(0, 10)
const newLine = (): LineDraft => ({
  key: crypto.randomUUID(), product_id: '', product_label: '', uom: '', quantity_ordered: '', unit_cost: '',
})

export function POFormModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [supplierId, setSupplierId] = useState('')
  const [supplierLabel, setSupplierLabel] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [orderDate, setOrderDate] = useState(today())
  const [expectedDate, setExpectedDate] = useState('')
  const [lines, setLines] = useState<LineDraft[]>([newLine()])

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses', 'all'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
    enabled: open,
  })

  const reset = () => {
    setSupplierId(''); setSupplierLabel(''); setWarehouseId('')
    setOrderDate(today()); setExpectedDate(''); setLines([newLine()])
  }

  const updateLine = (key: string, patch: Partial<LineDraft>) =>
    setLines(ls => ls.map(l => (l.key === key ? { ...l, ...patch } : l)))

  const validLines = lines.filter(l => l.product_id && Number(l.quantity_ordered) > 0)
  const canSubmit = supplierId && warehouseId && orderDate && validLines.length > 0

  const estimatedTotal = validLines.reduce(
    (sum, l) => sum + Number(l.quantity_ordered) * Number(l.unit_cost || 0), 0,
  )

  const createMut = useMutation({
    mutationFn: () => inboundApi.createPO({
      warehouse_id: warehouseId,
      supplier_id: supplierId,
      order_date: orderDate,
      expected_delivery_date: expectedDate || undefined,
      lines: validLines.map(l => ({
        product_id: l.product_id,
        quantity_ordered: Number(l.quantity_ordered),
        unit_cost: l.unit_cost ? Number(l.unit_cost) : undefined,
      })),
    }),
    onSuccess: () => {
      toast.success('Orden de compra creada')
      qc.invalidateQueries({ queryKey: ['pos'] })
      reset(); onClose()
    },
    onError: () => toast.error('No se pudo crear la orden de compra'),
  })

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose() }}
      title="Nueva Orden de Compra"
      description="Define proveedor, bodega de destino y las líneas a ordenar."
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={() => { reset(); onClose() }}>Cancelar</Button>
          <Button size="sm" loading={createMut.isPending} disabled={!canSubmit}
            onClick={() => createMut.mutate()}>
            Crear OC
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Combobox<Supplier>
            label="Proveedor"
            placeholder="Buscar por código o nombre…"
            value={supplierId}
            displayLabel={supplierLabel}
            queryKey="suppliers"
            fetcher={s => masterApi.getSuppliers({ search: s, page_size: 20, status: 'active' })}
            getKey={x => x.id}
            getLabel={x => `${x.code} — ${x.name}`}
            onSelect={x => { setSupplierId(x.id); setSupplierLabel(`${x.code} — ${x.name}`) }}
          />
          <Select
            label="Bodega"
            placeholder="Selecciona bodega"
            value={warehouseId}
            onChange={e => setWarehouseId(e.target.value)}
            options={(warehouses?.items ?? []).map(w => ({ value: w.id, label: `${w.code} — ${w.name}` }))}
          />
          <Input label="Fecha de orden" type="date" value={orderDate}
            onChange={e => setOrderDate(e.target.value)} />
          <Input label="Entrega esperada" type="date" value={expectedDate}
            onChange={e => setExpectedDate(e.target.value)} />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-800">Líneas</h3>
            <Button variant="ghost" size="sm" onClick={() => setLines(ls => [...ls, newLine()])}>
              <Plus className="h-4 w-4" /> Agregar línea
            </Button>
          </div>

          <div className="space-y-2">
            {lines.map(line => (
              <div key={line.key} className="grid grid-cols-12 items-end gap-2 rounded-lg border border-gray-100 bg-gray-50/50 p-2">
                <div className="col-span-6">
                  <Combobox<Product>
                    placeholder="Producto (SKU o nombre)…"
                    value={line.product_id}
                    displayLabel={line.product_label}
                    queryKey="products"
                    fetcher={s => masterApi.getProducts({ search: s, page_size: 20, status: 'active' })}
                    getKey={x => x.id}
                    getLabel={x => `${x.sku} — ${x.name}`}
                    onSelect={x => updateLine(line.key, {
                      product_id: x.id, product_label: `${x.sku} — ${x.name}`, uom: x.uom,
                    })}
                  />
                </div>
                <div className="col-span-2">
                  <Input placeholder="Cant." type="number" min="0" step="0.01"
                    value={line.quantity_ordered}
                    onChange={e => updateLine(line.key, { quantity_ordered: e.target.value })} />
                </div>
                <div className="col-span-2">
                  <Input placeholder="Costo U." type="number" min="0" step="0.0001"
                    value={line.unit_cost}
                    onChange={e => updateLine(line.key, { unit_cost: e.target.value })} />
                </div>
                <div className="col-span-1 pb-1 text-center text-xs text-gray-400">{line.uom || '—'}</div>
                <div className="col-span-1 flex justify-end pb-1">
                  <button
                    type="button"
                    onClick={() => setLines(ls => ls.length > 1 ? ls.filter(l => l.key !== line.key) : ls)}
                    title="Quitar línea"
                    className="text-gray-400 hover:text-red-600 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end pt-1 text-sm text-gray-600">
            Total estimado:&nbsp;<span className="font-semibold text-gray-900">{fmt.currency(estimatedTotal)}</span>
          </div>
        </div>
      </div>
    </Modal>
  )
}
