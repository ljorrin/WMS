import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Send, DollarSign } from 'lucide-react'
import { inboundApi, masterApi, warehouseApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Combobox } from '@/components/ui/Combobox'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { Supplier } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20

export function RTVListPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['rtvs', page],
    queryFn: () => inboundApi.getRTVs({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  // Form state
  const [warehouseId, setWarehouseId] = useState('')
  const [supplierId, setSupplierId] = useState('')
  const [supplierLabel, setSupplierLabel] = useState('')
  const [reason, setReason] = useState('')
  const [creditExpected, setCreditExpected] = useState('')

  const resetForm = () => {
    setWarehouseId(''); setSupplierId(''); setSupplierLabel(''); setReason(''); setCreditExpected('')
  }

  const createMut = useMutation({
    mutationFn: () => inboundApi.createRTV({
      warehouse_id: warehouseId,
      supplier_id: supplierId,
      reason,
      credit_expected: creditExpected ? Number(creditExpected) : 0,
    }),
    onSuccess: () => {
      toast.success('RTV creada')
      setOpen(false); resetForm()
      qc.invalidateQueries({ queryKey: ['rtvs'] })
    },
  })

  const shipMut = useMutation({
    mutationFn: (id: string) => inboundApi.shipRTV(id, {}),
    onSuccess: () => { toast.success('RTV despachada'); qc.invalidateQueries({ queryKey: ['rtvs'] }) },
  })

  const creditMut = useMutation({
    mutationFn: (id: string) => inboundApi.creditRTV(id, {}),
    onSuccess: () => { toast.success('Crédito registrado'); qc.invalidateQueries({ queryKey: ['rtvs'] }) },
  })

  const formValid = warehouseId && supplierId && reason.length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Devoluciones a Proveedor (RTV)</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} devoluciones</p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nueva RTV
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Proveedor</Th>
              <Th>Motivo</Th>
              <Th>Crédito esperado</Th>
              <Th>Crédito recibido</Th>
              <Th>Creado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 8 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-16" /></Td>
                  ))}
                </Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={8} message="No hay devoluciones a proveedor registradas" />
            ) : (
              data.items.map(rtv => (
                <Tr key={rtv.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{rtv.rtv_number}</span></Td>
                  <Td><Badge status={rtv.status} /></Td>
                  <Td className="text-gray-600">{rtv.supplier_name ?? rtv.supplier_id}</Td>
                  <Td className="text-gray-600 max-w-[240px] truncate" title={rtv.reason}>{rtv.reason}</Td>
                  <Td>{fmt.currency(rtv.credit_expected)}</Td>
                  <Td>{fmt.currency(rtv.credit_received)}</Td>
                  <Td className="text-xs text-gray-400">{fmt.date(rtv.created_at)}</Td>
                  <Td>
                    <div className="flex gap-2">
                      {rtv.status === 'approved' && (
                        <button onClick={() => shipMut.mutate(rtv.id)} title="Despachar"
                          className="text-blue-600 hover:text-blue-800 transition-colors">
                          <Send className="h-4 w-4" />
                        </button>
                      )}
                      {rtv.status === 'shipped' && (
                        <button onClick={() => creditMut.mutate(rtv.id)} title="Registrar crédito"
                          className="text-green-600 hover:text-green-800 transition-colors">
                          <DollarSign className="h-4 w-4" />
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
        title="Nueva devolución a proveedor"
        description="Crea una RTV manual indicando el proveedor y el motivo del retorno."
        size="md"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={!formValid} loading={createMut.isPending}
              onClick={() => createMut.mutate()}>Crear RTV</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Bodega</label>
            <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              <option value="">Seleccionar…</option>
              {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Proveedor</label>
            <Combobox<Supplier>
              placeholder="Buscar proveedor…"
              value={supplierId}
              displayLabel={supplierLabel}
              queryKey="suppliers-rtv"
              fetcher={s => masterApi.getSuppliers({ search: s, page_size: 20 })}
              getKey={s => s.id}
              getLabel={s => `${s.code} — ${s.name}`}
              onSelect={s => { setSupplierId(s.id); setSupplierLabel(`${s.code} — ${s.name}`) }}
            />
          </div>
          <Input label="Motivo" value={reason} onChange={e => setReason(e.target.value)}
            placeholder="Motivo de la devolución" />
          <Input label="Crédito esperado (USD)" type="number" value={creditExpected}
            onChange={e => setCreditExpected(e.target.value)} placeholder="0.00" />
        </div>
      </Modal>
    </div>
  )
}
