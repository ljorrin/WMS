import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Waves, Zap, ListPlus, Users, Layers } from 'lucide-react'
import { streamingApi, outboundApi, warehouseApi } from '@/api/endpoints'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { KpiCard } from '@/components/ui/KpiCard'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'
import { useAuthStore } from '@/store/authStore'
import toast from 'react-hot-toast'

export function StreamingPage() {
  const [warehouseId, setWarehouseId] = useState('')
  const [enqueueOpen, setEnqueueOpen] = useState(false)
  const qc = useQueryClient()
  const { user } = useAuthStore()

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const { data: metrics, isLoading: loadingMetrics } = useQuery({
    queryKey: ['streaming-metrics', warehouseId],
    queryFn: () => streamingApi.getMetrics(warehouseId || undefined),
  })

  const { data: queue, isLoading: loadingQueue } = useQuery({
    queryKey: ['streaming-queue', warehouseId],
    queryFn: () => streamingApi.getQueue(warehouseId || undefined),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['streaming-metrics'] })
    qc.invalidateQueries({ queryKey: ['streaming-queue'] })
  }

  const nextMut = useMutation({
    mutationFn: () => streamingApi.next(warehouseId, user!.id),
    onSuccess: (task) => {
      if (task) toast.success('Tarea despachada — orden waveless asignada')
      else toast('Cola vacía o WIP máximo alcanzado', { icon: 'ℹ️' })
      invalidate()
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Error al despachar'),
  })

  // Enqueue por SO
  const { data: eligibleSOs } = useQuery({
    queryKey: ['eligible-sos-streaming', warehouseId, enqueueOpen],
    queryFn: () => outboundApi.getSOs({
      page: 1, page_size: 100, status: 'confirmed',
      ...(warehouseId ? { warehouse_id: warehouseId } : {}),
    }),
    enabled: enqueueOpen,
  })
  const [selectedSO, setSelectedSO] = useState('')

  const enqueueMut = useMutation({
    mutationFn: () => streamingApi.enqueueOrder(selectedSO),
    onSuccess: (res) => {
      toast.success(`${res.tasks_created} tareas waveless generadas`)
      setEnqueueOpen(false); setSelectedSO('')
      invalidate()
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Error al encolar la orden'),
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Waves className="h-5 w-5 text-primary-600" /> Order Streaming (Waveless)
          </h1>
          <p className="text-sm text-gray-500">Liberación continua de picking, sin esperar a llenar una ola.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
            <option value="">Todas las bodegas</option>
            {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
          </select>
          <Button size="sm" variant="secondary" onClick={() => setEnqueueOpen(true)}>
            <ListPlus className="h-4 w-4" /> Encolar Orden
          </Button>
          <Button size="sm" disabled={!warehouseId} loading={nextMut.isPending}
            onClick={() => nextMut.mutate()} title={!warehouseId ? 'Selecciona una bodega' : ''}>
            <Zap className="h-4 w-4" /> Traer Siguiente Tarea
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard title="Cola Pendiente" value={metrics?.queue_pending ?? 0}
          subtitle="Sin ola, sin asignar" icon={Layers} loading={loadingMetrics} />
        <KpiCard title="En Curso" value={metrics?.in_progress ?? 0} icon={Waves} loading={loadingMetrics} />
        <KpiCard title="Operadores Activos" value={metrics?.operators_active ?? 0}
          icon={Users} loading={loadingMetrics} />
      </div>

      <Card padding={false}>
        <CardHeader className="p-5 pb-0"><CardTitle>Cola Waveless</CardTitle></CardHeader>
        <Table>
          <Thead>
            <Tr><Th>Producto</Th><Th>Cantidad</Th><Th>Estado</Th><Th>Prioridad</Th></Tr>
          </Thead>
          <Tbody>
            {loadingQueue ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 4 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-14" /></Td>
                ))}</Tr>
              ))
            ) : !queue?.items.length ? (
              <EmptyRow cols={4} message="Cola waveless vacía" />
            ) : (
              queue.items.map(t => (
                <Tr key={t.id}>
                  <Td className="font-mono text-xs">{t.product_name ?? t.product_id.slice(0, 8)}</Td>
                  <Td>{fmt.number(t.quantity_requested)}</Td>
                  <Td><Badge status={t.status} /></Td>
                  <Td className="text-center">{t.priority}</Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
      </Card>

      <Modal open={enqueueOpen} onClose={() => setEnqueueOpen(false)} title="Encolar orden como waveless"
        description="Genera tareas de picking sin ola (wave_id = NULL) para las líneas asignadas de la orden."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setEnqueueOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={!selectedSO} loading={enqueueMut.isPending}
              onClick={() => enqueueMut.mutate()}>Encolar</Button>
          </>
        }>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Orden de venta confirmada</label>
          <select value={selectedSO} onChange={e => setSelectedSO(e.target.value)}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
            <option value="">Seleccionar…</option>
            {eligibleSOs?.items.map(so => (
              <option key={so.id} value={so.id}>{so.so_number}</option>
            ))}
          </select>
          {!eligibleSOs?.items.length && (
            <p className="text-xs text-gray-400 mt-2">No hay órdenes confirmadas disponibles.</p>
          )}
        </div>
      </Modal>
    </div>
  )
}
