import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, PackageOpen, RotateCcw } from 'lucide-react'
import { outboundApi, warehouseApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { ReturnOrder } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const RETURN_TYPES = [
  { value: 'refund', label: 'Reembolso' },
  { value: 'exchange', label: 'Cambio' },
  { value: 'credit', label: 'Nota de crédito' },
]

export function ReturnsPage() {
  const [page, setPage] = useState(1)
  const [createOpen, setCreateOpen] = useState(false)
  const [target, setTarget] = useState<ReturnOrder | null>(null)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['returns', page],
    queryFn: () => outboundApi.getReturns({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  // Form crear RMA
  const [warehouseId, setWarehouseId] = useState('')
  const [customerId, setCustomerId] = useState('')
  const [soId, setSoId] = useState('')
  const [reason, setReason] = useState('')
  const [returnType, setReturnType] = useState('refund')
  const [createNotes, setCreateNotes] = useState('')

  // Form recibir RMA
  const [inspectionNotes, setInspectionNotes] = useState('')
  const [restockEligible, setRestockEligible] = useState(false)
  const [restockLocation, setRestockLocation] = useState('')
  const [refundAmount, setRefundAmount] = useState('0')

  const resetCreate = () => {
    setWarehouseId(''); setCustomerId(''); setSoId(''); setReason(''); setReturnType('refund'); setCreateNotes('')
  }
  const resetReceive = () => {
    setInspectionNotes(''); setRestockEligible(false); setRestockLocation(''); setRefundAmount('0')
  }

  const createMut = useMutation({
    mutationFn: () => outboundApi.createReturn({
      warehouse_id: warehouseId,
      customer_id: customerId,
      so_id: soId || undefined,
      reason,
      return_type: returnType,
      notes: createNotes || undefined,
    }),
    onSuccess: () => {
      toast.success('RMA creada — solicitud registrada')
      setCreateOpen(false); resetCreate()
      qc.invalidateQueries({ queryKey: ['returns'] })
    },
  })

  const receiveMut = useMutation({
    mutationFn: () => outboundApi.receiveReturn(target!.id, {
      inspection_notes: inspectionNotes,
      restocking_eligible: restockEligible,
      restocking_location_id: restockEligible && restockLocation ? restockLocation : undefined,
      refund_amount: Number(refundAmount) || 0,
    }),
    onSuccess: () => {
      toast.success('Devolución recibida e inspeccionada')
      setTarget(null); resetReceive()
      qc.invalidateQueries({ queryKey: ['returns'] })
    },
  })

  const createValid = warehouseId && customerId && reason.length >= 3
  const receiveValid = inspectionNotes.length >= 3 && (!restockEligible || restockLocation.length > 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Devoluciones (RMA)</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} devoluciones</p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Nueva RMA
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Tipo</Th>
              <Th>Motivo</Th>
              <Th>Reembolso</Th>
              <Th>Recibido</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-16" /></Td>
                  ))}
                </Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={7} message="No hay devoluciones registradas" />
            ) : (
              data.items.map(r => (
                <Tr key={r.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{r.rma_number}</span></Td>
                  <Td><Badge status={r.status} /></Td>
                  <Td className="text-xs text-gray-500 capitalize">{r.return_type}</Td>
                  <Td className="text-gray-600 text-sm max-w-xs truncate">{r.reason}</Td>
                  <Td className="font-medium">{r.refund_amount > 0 ? fmt.currency(r.refund_amount) : '—'}</Td>
                  <Td className="text-xs text-gray-400">{fmt.date(r.received_at)}</Td>
                  <Td>
                    {(r.status === 'requested' || r.status === 'approved' || r.status === 'in_transit') && (
                      <Button size="sm" variant="secondary" onClick={() => setTarget(r)}>
                        <PackageOpen className="h-4 w-4" /> Recibir
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      {/* Crear RMA */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Nueva devolución (RMA)"
        description="Registra una solicitud de devolución de cliente."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setCreateOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={!createValid} loading={createMut.isPending}
              onClick={() => createMut.mutate()}>Crear RMA</Button>
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
              <label className="text-sm font-medium text-gray-700">Tipo de devolución</label>
              <select value={returnType} onChange={e => setReturnType(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {RETURN_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
          </div>
          <Input label="Customer ID (UUID)" value={customerId}
            onChange={e => setCustomerId(e.target.value)} placeholder="UUID del cliente" />
          <Input label="Sales Order ID (opcional)" value={soId}
            onChange={e => setSoId(e.target.value)} placeholder="UUID de la orden original" />
          <Input label="Motivo" value={reason}
            onChange={e => setReason(e.target.value)} placeholder="Motivo de la devolución (mín. 3 caracteres)" />
          <Input label="Notas (opcional)" value={createNotes}
            onChange={e => setCreateNotes(e.target.value)} />
        </div>
      </Modal>

      {/* Recibir RMA */}
      <Modal
        open={!!target}
        onClose={() => setTarget(null)}
        title={`Recibir devolución ${target?.rma_number ?? ''}`}
        description="Inspecciona el material devuelto y define su disposición."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setTarget(null)}>Cancelar</Button>
            <Button size="sm" disabled={!receiveValid} loading={receiveMut.isPending}
              onClick={() => receiveMut.mutate()}>
              <RotateCcw className="h-4 w-4" /> Confirmar recepción
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="Notas de inspección" value={inspectionNotes}
            onChange={e => setInspectionNotes(e.target.value)}
            placeholder="Estado del material recibido (mín. 3 caracteres)" />
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" className="rounded" checked={restockEligible}
              onChange={e => setRestockEligible(e.target.checked)} />
            Material apto para reingreso a inventario (restocking)
          </label>
          {restockEligible && (
            <Input label="Ubicación de reingreso (Location ID)" value={restockLocation}
              onChange={e => setRestockLocation(e.target.value)} placeholder="UUID de la ubicación" />
          )}
          <Input label="Monto a reembolsar (USD)" type="number" value={refundAmount}
            onChange={e => setRefundAmount(e.target.value)} placeholder="0.00" />
        </div>
      </Modal>
    </div>
  )
}
