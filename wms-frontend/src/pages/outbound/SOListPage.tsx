import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, CheckCircle, Zap } from 'lucide-react'
import { outboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'
import { cn } from '@/utils/cn'
import toast from 'react-hot-toast'

const PRIORITY_LABEL: Record<number, { label: string; cls: string }> = {
  1: { label: 'Urgente', cls: 'text-red-600 font-bold' },
  2: { label: 'Alta', cls: 'text-orange-600 font-semibold' },
  5: { label: 'Normal', cls: 'text-gray-600' },
  8: { label: 'Baja', cls: 'text-gray-400' },
  10: { label: 'Mínima', cls: 'text-gray-300' },
}

function PriorityLabel({ p }: { p: number }) {
  const def = p <= 2 ? PRIORITY_LABEL[p <= 1 ? 1 : 2]
    : p <= 4 ? PRIORITY_LABEL[2]
    : p <= 6 ? PRIORITY_LABEL[5]
    : p <= 8 ? PRIORITY_LABEL[8]
    : PRIORITY_LABEL[10]

  return <span className={cn('text-xs', def.cls)}>{def.label}</span>
}

export function SOListPage() {
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string[]>([])
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['sos', page],
    queryFn: () => outboundApi.getSOs({ page, page_size: 20 }),
    placeholderData: prev => prev,
  })

  const confirmMut = useMutation({
    mutationFn: (id: string) => outboundApi.confirmSO(id),
    onSuccess: () => {
      toast.success('SO confirmada — stock reservado')
      qc.invalidateQueries({ queryKey: ['sos'] })
    },
  })

  const waveMut = useMutation({
    mutationFn: () => outboundApi.createWave({
      warehouse_id: data?.items[0]?.warehouse_id ?? '',
      so_ids: selected,
      picking_method: 'batch',
      priority: 5,
    }),
    onSuccess: () => {
      toast.success(`Wave creada con ${selected.length} órdenes`)
      setSelected([])
      qc.invalidateQueries({ queryKey: ['sos'] })
    },
  })

  const toggleSelect = (id: string) =>
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Órdenes de Venta</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} órdenes</p>
        </div>
        <div className="flex gap-2">
          {selected.length > 0 && (
            <Button size="sm" onClick={() => waveMut.mutate()} loading={waveMut.isPending}>
              <Zap className="h-4 w-4" /> Crear Wave ({selected.length})
            </Button>
          )}
          <Button size="sm" variant={selected.length > 0 ? 'secondary' : 'primary'}>
            <Plus className="h-4 w-4" /> Nueva SO
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th className="w-8">
                <input type="checkbox" className="rounded" readOnly />
              </Th>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Cliente</Th>
              <Th>Prioridad</Th>
              <Th>Fecha</Th>
              <Th>Entrega Solicitada</Th>
              <Th>Total</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 9 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-16" /></Td>
                  ))}
                </Tr>
              ))
            ) : data?.items.length === 0 ? (
              <EmptyRow cols={9} message="No hay órdenes de venta" />
            ) : (
              data?.items.map(so => {
                const isOverdue = so.requested_delivery_date
                  && new Date(so.requested_delivery_date) < new Date()
                  && !['shipped', 'delivered', 'cancelled'].includes(so.status)

                return (
                  <Tr key={so.id} className={isOverdue ? 'bg-red-50/40' : ''}>
                    <Td>
                      {['confirmed', 'allocated'].includes(so.status) && (
                        <input
                          type="checkbox"
                          className="rounded"
                          checked={selected.includes(so.id)}
                          onChange={() => toggleSelect(so.id)}
                        />
                      )}
                    </Td>
                    <Td>
                      <span className="font-mono font-medium text-primary-700">{so.so_number}</span>
                    </Td>
                    <Td><Badge status={so.status} /></Td>
                    <Td className="text-gray-600 text-xs">{so.customer_id}</Td>
                    <Td><PriorityLabel p={so.priority} /></Td>
                    <Td className="text-xs">{fmt.date(so.order_date)}</Td>
                    <Td className={cn('text-xs', isOverdue && 'text-red-600 font-semibold')}>
                      {fmt.date(so.requested_delivery_date)}
                    </Td>
                    <Td className="font-medium">{fmt.currency(so.total_amount, so.currency)}</Td>
                    <Td>
                      {so.status === 'draft' && (
                        <button
                          onClick={() => confirmMut.mutate(so.id)}
                          title="Confirmar SO"
                          className="text-green-600 hover:text-green-800 transition-colors"
                        >
                          <CheckCircle className="h-4 w-4" />
                        </button>
                      )}
                    </Td>
                  </Tr>
                )
              })
            )}
          </Tbody>
        </Table>

        {data && data.total > 20 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <p className="text-xs text-gray-500">
              {(page - 1) * 20 + 1}–{Math.min(page * 20, data.total)} de {data.total}
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page === 1}
                onClick={() => setPage(p => p - 1)}>Anterior</Button>
              <Button variant="secondary" size="sm"
                disabled={page * 20 >= data.total}
                onClick={() => setPage(p => p + 1)}>Siguiente</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
