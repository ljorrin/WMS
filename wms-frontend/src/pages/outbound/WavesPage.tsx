import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Send, Layers } from 'lucide-react'
import { outboundApi, warehouseApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import { cn } from '@/utils/cn'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const PICKING_METHODS = ['discrete', 'batch', 'zone', 'cluster', 'wave']

export function WavesPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['waves', page],
    queryFn: () => outboundApi.getWaves({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  // Form
  const [warehouseId, setWarehouseId] = useState('')
  const [pickingMethod, setPickingMethod] = useState('discrete')
  const [priority, setPriority] = useState(5)
  const [selectedSOs, setSelectedSOs] = useState<string[]>([])

  // Órdenes elegibles para wave (confirmadas / asignadas, sin wave previa)
  const { data: eligible } = useQuery({
    queryKey: ['eligible-sos', warehouseId, open],
    queryFn: () => outboundApi.getSOs({
      page: 1, page_size: 100, status: 'confirmed',
      ...(warehouseId ? { warehouse_id: warehouseId } : {}),
    }),
    enabled: open,
  })

  const resetForm = () => {
    setWarehouseId(''); setPickingMethod('discrete'); setPriority(5); setSelectedSOs([])
  }

  const createMut = useMutation({
    mutationFn: () => outboundApi.createWave({
      warehouse_id: warehouseId,
      so_ids: selectedSOs,
      picking_method: pickingMethod,
      priority,
    }),
    onSuccess: () => {
      toast.success('Wave creada — lista para liberar')
      setOpen(false); resetForm()
      qc.invalidateQueries({ queryKey: ['waves'] })
    },
  })

  const releaseMut = useMutation({
    mutationFn: (id: string) => outboundApi.releaseWave(id),
    onSuccess: () => {
      toast.success('Wave liberada — tareas de picking generadas')
      qc.invalidateQueries({ queryKey: ['waves'] })
    },
  })

  const toggleSO = (id: string) =>
    setSelectedSOs(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const formValid = warehouseId && selectedSOs.length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Waves de Picking</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} waves</p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nueva Wave
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Método</Th>
              <Th>Prioridad</Th>
              <Th>Órdenes</Th>
              <Th>Líneas</Th>
              <Th>Unidades</Th>
              <Th>Liberada</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 9 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-14" /></Td>
                  ))}
                </Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={9} message="No hay waves registradas" />
            ) : (
              data.items.map(w => (
                <Tr key={w.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{w.wave_number}</span></Td>
                  <Td><Badge status={w.status} /></Td>
                  <Td className="text-xs text-gray-500 capitalize">{w.picking_method}</Td>
                  <Td className="text-center">{w.priority}</Td>
                  <Td className="text-center">{w.total_orders}</Td>
                  <Td className="text-center">{w.total_lines}</Td>
                  <Td>{fmt.number(w.total_units)}</Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(w.released_at)}</Td>
                  <Td>
                    {w.status === 'open' && (
                      <button onClick={() => releaseMut.mutate(w.id)} title="Liberar wave"
                        className="inline-flex items-center gap-1 text-green-600 hover:text-green-800 transition-colors text-sm">
                        <Send className="h-4 w-4" /> Liberar
                      </button>
                    )}
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
        title="Nueva wave de picking"
        description="Agrupa órdenes confirmadas para liberarlas como un lote de picking."
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={!formValid} loading={createMut.isPending}
              onClick={() => createMut.mutate()}>Crear wave</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Bodega</label>
              <select value={warehouseId} onChange={e => { setWarehouseId(e.target.value); setSelectedSOs([]) }}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                <option value="">Seleccionar…</option>
                {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Método</label>
              <select value={pickingMethod} onChange={e => setPickingMethod(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {PICKING_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Prioridad</label>
              <select value={priority} onChange={e => setPriority(Number(e.target.value))}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {Array.from({ length: 10 }, (_, i) => i + 1).map(p => (
                  <option key={p} value={p}>{p}{p === 1 ? ' (urgente)' : p === 10 ? ' (normal)' : ''}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 flex items-center gap-1">
                <Layers className="h-4 w-4" /> Órdenes elegibles ({selectedSOs.length} seleccionadas)
              </label>
            </div>
            {!warehouseId ? (
              <p className="text-sm text-gray-400 py-4 text-center">Selecciona una bodega para ver órdenes confirmadas.</p>
            ) : !eligible?.items.length ? (
              <p className="text-sm text-gray-400 py-4 text-center">No hay órdenes confirmadas disponibles.</p>
            ) : (
              <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-200 divide-y divide-gray-50">
                {eligible.items.map(so => (
                  <label key={so.id}
                    className={cn('flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-gray-50',
                      selectedSOs.includes(so.id) && 'bg-primary-50')}>
                    <input type="checkbox" className="rounded" checked={selectedSOs.includes(so.id)}
                      onChange={() => toggleSO(so.id)} />
                    <span className="font-mono font-medium text-primary-700">{so.so_number}</span>
                    <span className="text-gray-400 text-xs ml-auto">{so.lines?.length ?? 0} líneas · prio {so.priority}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}
