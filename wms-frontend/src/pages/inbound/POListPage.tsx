import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, CheckCircle, XCircle, Pencil, Trash2 } from 'lucide-react'
import { inboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'
import toast from 'react-hot-toast'
import { POFormModal } from './POFormModal'
import { PODetailModal } from './PODetailModal'
import { POEditModal } from './POEditModal'
import type { PurchaseOrder } from '@/types'

export function POListPage() {
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [editing, setEditing] = useState<PurchaseOrder | null>(null)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['pos', page],
    queryFn: () => inboundApi.getPOs({ page, page_size: 20 }),
    placeholderData: prev => prev,
  })

  const confirmMut = useMutation({
    mutationFn: (id: string) => inboundApi.confirmPO(id),
    onSuccess: () => {
      toast.success('OC confirmada')
      qc.invalidateQueries({ queryKey: ['pos'] })
    },
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => inboundApi.cancelPO(id),
    onSuccess: () => {
      toast.success('OC cancelada')
      qc.invalidateQueries({ queryKey: ['pos'] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => inboundApi.deletePO(id),
    onSuccess: () => {
      toast.success('OC eliminada')
      qc.invalidateQueries({ queryKey: ['pos'] })
    },
    onError: () => toast.error('No se pudo eliminar la OC'),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Órdenes de Compra</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} órdenes</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> Nueva OC
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Proveedor</Th>
              <Th>Fecha Orden</Th>
              <Th>Entrega Esperada</Th>
              <Th>Total</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                  ))}
                </Tr>
              ))
            ) : data?.items.length === 0 ? (
              <EmptyRow cols={7} message="No hay órdenes de compra" />
            ) : (
              data?.items.map(po => (
                <Tr key={po.id}>
                  <Td>
                    <button onClick={() => setDetailId(po.id)}
                      className="font-mono font-medium text-primary-700 hover:text-primary-900 hover:underline">
                      {po.po_number}
                    </button>
                  </Td>
                  <Td><Badge status={po.status} /></Td>
                  <Td className="text-gray-600">{po.supplier_name ?? po.supplier_id}</Td>
                  <Td>{fmt.date(po.order_date)}</Td>
                  <Td>
                    {po.expected_delivery_date ? (
                      <span className={new Date(po.expected_delivery_date) < new Date() && po.status !== 'closed'
                        ? 'text-red-600 font-medium' : ''}>
                        {fmt.date(po.expected_delivery_date)}
                      </span>
                    ) : '—'}
                  </Td>
                  <Td className="font-medium">{fmt.currency(po.total_amount, po.currency)}</Td>
                  <Td>
                    <div className="flex gap-1">
                      {po.status === 'draft' && (
                        <button
                          onClick={() => setEditing(po)}
                          title="Editar OC"
                          className="text-gray-500 hover:text-primary-700 transition-colors"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                      )}
                      {po.status === 'draft' && (
                        <button
                          onClick={() => confirmMut.mutate(po.id)}
                          title="Confirmar OC"
                          className="text-green-600 hover:text-green-800 transition-colors"
                        >
                          <CheckCircle className="h-4 w-4" />
                        </button>
                      )}
                      {!['closed', 'cancelled'].includes(po.status) && (
                        <button
                          onClick={() => cancelMut.mutate(po.id)}
                          title="Cancelar OC"
                          className="text-red-500 hover:text-red-700 transition-colors"
                        >
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                      {['draft', 'cancelled'].includes(po.status) && (
                        <button
                          onClick={() => {
                            if (confirm(`¿Eliminar la orden ${po.po_number}? Esta acción la oculta del listado.`))
                              deleteMut.mutate(po.id)
                          }}
                          title="Eliminar OC (borrado lógico)"
                          className="text-gray-400 hover:text-red-700 transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))
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

      <POFormModal open={creating} onClose={() => setCreating(false)} />
      <PODetailModal poId={detailId} onClose={() => setDetailId(null)} />
      <POEditModal po={editing} onClose={() => setEditing(null)} />
    </div>
  )
}
