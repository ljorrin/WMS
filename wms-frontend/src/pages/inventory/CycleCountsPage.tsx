import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, ListChecks, CheckCircle2 } from 'lucide-react'
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

const PAGE_SIZE = 20
const COUNT_TYPES = [
  { value: 'cyclic', label: 'Cíclico' },
  { value: 'full_physical', label: 'Físico total' },
  { value: 'blind', label: 'Ciego' },
  { value: 'discrepancy', label: 'Por discrepancia' },
  { value: 'abc_rotation', label: 'Rotación ABC' },
]

export function CycleCountsPage() {
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['cycle-counts', page],
    queryFn: () => inventoryApi.getCycleCounts({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const { data: detail } = useQuery({
    queryKey: ['cycle-count', detailId],
    queryFn: () => inventoryApi.getCycleCount(detailId as string),
    enabled: !!detailId,
  })

  // Form
  const [warehouseId, setWarehouseId] = useState('')
  const [name, setName] = useState('')
  const [countType, setCountType] = useState('cyclic')

  const resetForm = () => { setWarehouseId(''); setName(''); setCountType('cyclic') }

  const createMut = useMutation({
    mutationFn: () => inventoryApi.createCycleCount({
      warehouse_id: warehouseId, name, count_type: countType,
    }),
    onSuccess: (res) => {
      toast.success(res.message)
      setOpen(false); resetForm()
      qc.invalidateQueries({ queryKey: ['cycle-counts'] })
    },
  })

  const [counts, setCounts] = useState<Record<string, string>>({})

  const saveResultsMut = useMutation({
    mutationFn: () => {
      const results = (detail?.lines ?? [])
        .filter(l => counts[l.id] !== undefined && counts[l.id] !== '')
        .map(l => ({
          location_id: l.location_id,
          product_id: l.product_id,
          batch_id: l.batch_id,
          quantity_counted: Number(counts[l.id]),
        }))
      return inventoryApi.recordCycleCountResults(detailId as string, results)
    },
    onSuccess: () => {
      toast.success('Conteos registrados')
      setCounts({})
      qc.invalidateQueries({ queryKey: ['cycle-count', detailId] })
    },
  })

  const completeMut = useMutation({
    mutationFn: (applyResults: boolean) => inventoryApi.completeCycleCount(detailId as string, applyResults),
    onSuccess: (res) => {
      toast.success(res.message)
      setDetailId(null)
      qc.invalidateQueries({ queryKey: ['cycle-counts'] })
    },
  })

  const formValid = warehouseId && name.length >= 3

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Conteos Cíclicos</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} conteos</p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nuevo Conteo
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Nombre</Th>
              <Th>Estado</Th>
              <Th>Tipo</Th>
              <Th>Líneas</Th>
              <Th>Precisión</Th>
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
              <EmptyRow cols={8} message="No hay conteos cíclicos registrados" />
            ) : (
              data.items.map(cc => (
                <Tr key={cc.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{cc.count_number}</span></Td>
                  <Td className="text-gray-700">{cc.name}</Td>
                  <Td><Badge status={cc.status} /></Td>
                  <Td className="text-xs text-gray-500 capitalize">{cc.count_type}</Td>
                  <Td className="text-center">{cc.total_lines}</Td>
                  <Td>{cc.accuracy_pct != null ? `${cc.accuracy_pct}%` : '—'}</Td>
                  <Td className="text-xs text-gray-400">{fmt.date(cc.created_at)}</Td>
                  <Td>
                    {cc.status === 'in_progress' && (
                      <button onClick={() => setDetailId(cc.id)} title="Registrar conteo"
                        className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 transition-colors text-sm">
                        <ListChecks className="h-4 w-4" /> Contar
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
        title="Nuevo conteo cíclico"
        description="Genera las líneas a contar según el stock actual de la bodega."
        size="md"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={!formValid} loading={createMut.isPending}
              onClick={() => createMut.mutate()}>Crear conteo</Button>
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
          <Input label="Nombre" value={name} onChange={e => setName(e.target.value)}
            placeholder="Ej: Conteo semanal zona A-01" />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Tipo de conteo</label>
            <select value={countType} onChange={e => setCountType(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              {COUNT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
        </div>
      </Modal>

      <Modal
        open={!!detailId}
        onClose={() => { setDetailId(null); setCounts({}) }}
        title={detail ? `Conteo ${detail.count_number} — ${detail.name}` : 'Conteo'}
        description="Registra la cantidad física contada por línea. Deja en blanco las que no se han contado."
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => { setDetailId(null); setCounts({}) }}>Cerrar</Button>
            <Button variant="secondary" size="sm" loading={saveResultsMut.isPending}
              onClick={() => saveResultsMut.mutate()}>Guardar conteos</Button>
            <Button size="sm" loading={completeMut.isPending}
              onClick={() => completeMut.mutate(true)}>
              <CheckCircle2 className="h-4 w-4" /> Completar y aplicar diferencias
            </Button>
          </>
        }
      >
        <Table>
          <Thead>
            <Tr>
              <Th>Ubicación</Th>
              <Th>Producto</Th>
              <Th>Sistema</Th>
              <Th>Contado</Th>
              <Th>Varianza</Th>
            </Tr>
          </Thead>
          <Tbody>
            {(detail?.lines ?? []).map(l => (
              <Tr key={l.id}>
                <Td className="text-xs">{l.location_code ?? l.location_id}</Td>
                <Td className="text-xs">{l.product_name ?? l.product_id}</Td>
                <Td>{fmt.number(l.quantity_system)}</Td>
                <Td className="w-28">
                  <input
                    type="number"
                    value={counts[l.id] ?? (l.quantity_counted ?? '')}
                    onChange={e => setCounts(prev => ({ ...prev, [l.id]: e.target.value }))}
                    className="h-8 w-24 rounded-lg border border-gray-300 px-2 text-sm"
                  />
                </Td>
                <Td className={l.variance ? (l.variance > 0 ? 'text-green-600' : 'text-red-600') : ''}>
                  {l.variance != null ? fmt.number(l.variance) : '—'}
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </Modal>
    </div>
  )
}
