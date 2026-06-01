import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, CheckCircle, PlayCircle, Trash2 } from 'lucide-react'
import { inventoryApi, warehouseApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import toast from 'react-hot-toast'

const REASON_CODES = ['DAMAGE', 'EXPIRED', 'COUNT_ERROR', 'THEFT', 'FOUND', 'OTHER']
const PAGE_SIZE = 20

interface DraftLine {
  product_id: string
  location_id: string
  quantity_system: string
  quantity_physical: string
}

const emptyLine = (): DraftLine => ({ product_id: '', location_id: '', quantity_system: '', quantity_physical: '' })

export function AdjustmentsPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['adjustments', page],
    queryFn: () => inventoryApi.getAdjustments({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  // Form state
  const [warehouseId, setWarehouseId] = useState('')
  const [reason, setReason] = useState('')
  const [reasonCode, setReasonCode] = useState('COUNT_ERROR')
  const [notes, setNotes] = useState('')
  const [lines, setLines] = useState<DraftLine[]>([emptyLine()])

  const resetForm = () => {
    setWarehouseId(''); setReason(''); setReasonCode('COUNT_ERROR'); setNotes(''); setLines([emptyLine()])
  }

  const createMut = useMutation({
    mutationFn: () => inventoryApi.createAdjustment({
      warehouse_id: warehouseId,
      reason,
      reason_code: reasonCode,
      notes: notes || undefined,
      lines: lines.map(l => ({
        product_id: l.product_id,
        location_id: l.location_id,
        quantity_system: Number(l.quantity_system),
        quantity_physical: Number(l.quantity_physical),
      })),
    }),
    onSuccess: () => {
      toast.success('Ajuste creado — pendiente de aprobación')
      setOpen(false); resetForm()
      qc.invalidateQueries({ queryKey: ['adjustments'] })
    },
  })

  const approveMut = useMutation({
    mutationFn: (id: string) => inventoryApi.approveAdjustment(id),
    onSuccess: () => { toast.success('Ajuste aprobado'); qc.invalidateQueries({ queryKey: ['adjustments'] }) },
  })

  const applyMut = useMutation({
    mutationFn: (id: string) => inventoryApi.applyAdjustment(id),
    onSuccess: () => { toast.success('Ajuste aplicado al inventario'); qc.invalidateQueries({ queryKey: ['adjustments'] }) },
  })

  const updateLine = (i: number, field: keyof DraftLine, value: string) =>
    setLines(prev => prev.map((l, idx) => idx === i ? { ...l, [field]: value } : l))

  const formValid = warehouseId && reason.length >= 5 &&
    lines.every(l => l.product_id && l.location_id && l.quantity_system !== '' && l.quantity_physical !== '')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Ajustes de Inventario</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} ajustes</p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nuevo Ajuste
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Motivo</Th>
              <Th># Líneas</Th>
              <Th>Creado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 6 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                  ))}
                </Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={6} message="No hay ajustes registrados" />
            ) : (
              data.items.map(adj => (
                <Tr key={adj.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{adj.adjustment_number}</span></Td>
                  <Td><Badge status={adj.status} /></Td>
                  <Td className="text-gray-600">{adj.reason}</Td>
                  <Td className="text-center">{adj.lines?.length ?? 0}</Td>
                  <Td className="text-xs text-gray-400">{fmt.date(adj.created_at)}</Td>
                  <Td>
                    <div className="flex gap-1">
                      {(adj.status === 'draft' || adj.status === 'pending_approval') && (
                        <button onClick={() => approveMut.mutate(adj.id)} title="Aprobar"
                          className="text-blue-600 hover:text-blue-800 transition-colors">
                          <CheckCircle className="h-4 w-4" />
                        </button>
                      )}
                      {adj.status === 'approved' && (
                        <button onClick={() => applyMut.mutate(adj.id)} title="Aplicar al inventario"
                          className="text-green-600 hover:text-green-800 transition-colors">
                          <PlayCircle className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Nuevo ajuste de inventario"
        description="El ajuste quedará pendiente de aprobación antes de afectar el stock."
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={!formValid} loading={createMut.isPending}
              onClick={() => createMut.mutate()}>Crear ajuste</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Bodega</label>
              <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                <option value="">Seleccionar…</option>
                {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Código de razón</label>
              <select value={reasonCode} onChange={e => setReasonCode(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {REASON_CODES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <Input label="Motivo" value={reason} onChange={e => setReason(e.target.value)}
            placeholder="Describe el motivo del ajuste (mín. 5 caracteres)" />

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">Líneas</label>
              <Button variant="ghost" size="sm" onClick={() => setLines(prev => [...prev, emptyLine()])}>
                <Plus className="h-4 w-4" /> Agregar línea
              </Button>
            </div>
            <div className="space-y-2">
              {lines.map((l, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-4">
                    <Input placeholder="Product ID (UUID)" value={l.product_id}
                      onChange={e => updateLine(i, 'product_id', e.target.value)} />
                  </div>
                  <div className="col-span-3">
                    <Input placeholder="Location ID" value={l.location_id}
                      onChange={e => updateLine(i, 'location_id', e.target.value)} />
                  </div>
                  <div className="col-span-2">
                    <Input type="number" placeholder="Sistema" value={l.quantity_system}
                      onChange={e => updateLine(i, 'quantity_system', e.target.value)} />
                  </div>
                  <div className="col-span-2">
                    <Input type="number" placeholder="Físico" value={l.quantity_physical}
                      onChange={e => updateLine(i, 'quantity_physical', e.target.value)} />
                  </div>
                  <div className="col-span-1 flex justify-center pb-2">
                    {lines.length > 1 && (
                      <button onClick={() => setLines(prev => prev.filter((_, idx) => idx !== i))}
                        className="text-red-500 hover:text-red-700" title="Eliminar línea">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Input label="Notas (opcional)" value={notes} onChange={e => setNotes(e.target.value)} />
        </div>
      </Modal>
    </div>
  )
}
