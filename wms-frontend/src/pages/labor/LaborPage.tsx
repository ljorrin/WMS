import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, PlayCircle, CheckCircle2, UserPlus, Zap,
  ClipboardList, Clock, Gauge, TrendingUp, ListChecks, Ruler,
} from 'lucide-react'
import { laborApi, warehouseApi } from '@/api/endpoints'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { KpiCard } from '@/components/ui/KpiCard'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import { useAuthStore } from '@/store/authStore'
import type { LaborActivityType } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const ACTIVITY_TYPES: LaborActivityType[] = [
  'pick', 'putaway', 'receive', 'pack', 'cycle_count', 'replenish', 'loading', 'unloading', 'transfer',
]
const STATUS_FILTERS = ['', 'pending', 'assigned', 'in_progress', 'completed', 'cancelled']

type Tab = 'dashboard' | 'tasks' | 'standards'

export function LaborPage() {
  const [tab, setTab] = useState<Tab>('dashboard')
  const [warehouseId, setWarehouseId] = useState('')

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const tabs: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: Gauge },
    { id: 'tasks', label: 'Cola de Tareas', icon: ClipboardList },
    { id: 'standards', label: 'Estándares', icon: Ruler },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Labor Management</h1>
          <p className="text-sm text-gray-500 mt-1">
            Estándares de ingeniería, ejecución de tareas e interleaving por proximidad.
          </p>
        </div>
        <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
          className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
          <option value="">Todas las bodegas</option>
          {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
        </select>
      </div>

      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-6" aria-label="Tabs">
          {tabs.map(t => {
            const isActive = tab === t.id
            const Icon = t.icon
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`group inline-flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm ${
                  isActive ? 'border-primary-600 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}>
                <Icon className={`h-4 w-4 ${isActive ? 'text-primary-600' : 'text-gray-400 group-hover:text-gray-500'}`} />
                {t.label}
              </button>
            )
          })}
        </nav>
      </div>

      {tab === 'dashboard' && <DashboardTab warehouseId={warehouseId} />}
      {tab === 'tasks' && <TasksTab warehouseId={warehouseId} />}
      {tab === 'standards' && <StandardsTab warehouseId={warehouseId} />}
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────
function DashboardTab({ warehouseId }: { warehouseId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['labor-dashboard', warehouseId],
    queryFn: () => laborApi.getDashboard(warehouseId || undefined),
  })

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard title="Tareas Completadas" value={data?.tasks_completed ?? 0}
          subtitle={`Últimos ${data?.window_days ?? 7} días`} icon={CheckCircle2} loading={isLoading} />
        <KpiCard title="En Cola / En Curso" value={`${data?.tasks_pending ?? 0} / ${data?.tasks_in_progress ?? 0}`}
          subtitle="Pendientes / en progreso" icon={ClipboardList} loading={isLoading} />
        <KpiCard title="Desempeño Promedio" value={fmt.pct(data?.avg_performance_pct)}
          subtitle="Estándar / real × 100" icon={TrendingUp} loading={isLoading} />
        <KpiCard title="Eficiencia de Labor" value={fmt.pct(data?.labor_efficiency_pct)}
          subtitle={`${fmt.number(data?.total_standard_hours)}h estándar / ${fmt.number(data?.total_actual_hours)}h reales`}
          icon={Clock} loading={isLoading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card padding={false}>
          <CardHeader className="p-5 pb-0">
            <CardTitle>Por Actividad</CardTitle>
          </CardHeader>
          <Table>
            <Thead>
              <Tr><Th>Actividad</Th><Th>Tareas</Th><Th>Desempeño</Th><Th>Hrs Est.</Th><Th>Hrs Real</Th></Tr>
            </Thead>
            <Tbody>
              {!data?.by_activity.length ? (
                <EmptyRow cols={5} message="Sin actividad en el período" />
              ) : data.by_activity.map(a => (
                <Tr key={a.activity_type}>
                  <Td className="capitalize">{a.activity_type.replace(/_/g, ' ')}</Td>
                  <Td className="text-center">{a.tasks_completed}</Td>
                  <Td>{fmt.pct(a.avg_performance_pct)}</Td>
                  <Td>{fmt.number(a.total_standard_hours)}</Td>
                  <Td>{fmt.number(a.total_actual_hours)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Card>

        <Card padding={false}>
          <CardHeader className="p-5 pb-0">
            <CardTitle>Ranking de Operadores</CardTitle>
          </CardHeader>
          <Table>
            <Thead>
              <Tr><Th>Operario</Th><Th>Tareas</Th><Th>Desempeño</Th><Th>Hrs Reales</Th></Tr>
            </Thead>
            <Tbody>
              {!data?.top_operators.length ? (
                <EmptyRow cols={4} message="Sin datos de operadores" />
              ) : data.top_operators.map(o => (
                <Tr key={o.user_id}>
                  <Td className="font-mono text-xs">{o.user_id.slice(0, 8)}</Td>
                  <Td className="text-center">{o.tasks_completed}</Td>
                  <Td className="text-green-600 font-medium">{fmt.pct(o.avg_performance_pct)}</Td>
                  <Td>{fmt.number(o.total_actual_hours)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Card>
      </div>
    </div>
  )
}

// ─── Cola de Tareas ───────────────────────────────────────
function TasksTab({ warehouseId }: { warehouseId: string }) {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const { user } = useAuthStore()

  const { data, isLoading } = useQuery({
    queryKey: ['labor-tasks', page, status, warehouseId],
    queryFn: () => laborApi.getTasks({
      page, page_size: PAGE_SIZE,
      ...(status ? { status } : {}),
      ...(warehouseId ? { warehouse_id: warehouseId } : {}),
    }),
    placeholderData: prev => prev,
  })

  // Form (crear tarea)
  const [activityType, setActivityType] = useState<LaborActivityType>('pick')
  const [quantity, setQuantity] = useState('1')
  const [zone, setZone] = useState('')
  const [priority, setPriority] = useState(5)
  const resetForm = () => { setActivityType('pick'); setQuantity('1'); setZone(''); setPriority(5) }

  const createMut = useMutation({
    mutationFn: () => laborApi.createTask({
      warehouse_id: warehouseId, activity_type: activityType,
      quantity: Number(quantity), zone: zone || undefined, priority,
    }),
    onSuccess: () => {
      toast.success('Tarea de labor creada')
      setOpen(false); resetForm()
      qc.invalidateQueries({ queryKey: ['labor-tasks'] })
    },
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['labor-tasks'] })

  const assignMut = useMutation({
    mutationFn: (id: string) => laborApi.assignTask(id, user!.id),
    onSuccess: () => { toast.success('Tarea asignada'); invalidate() },
  })
  const startMut = useMutation({
    mutationFn: (id: string) => laborApi.startTask(id),
    onSuccess: () => { toast.success('Tarea iniciada'); invalidate() },
  })
  const completeMut = useMutation({
    mutationFn: (id: string) => laborApi.completeTask(id),
    onSuccess: () => { toast.success('Tarea completada — desempeño calculado'); invalidate() },
  })
  const nextMut = useMutation({
    mutationFn: () => laborApi.assignNextTask(warehouseId, user!.id),
    onSuccess: (task) => {
      if (task) toast.success('Siguiente tarea asignada por interleaving')
      else toast('No hay tareas pendientes en cola', { icon: 'ℹ️' })
      invalidate()
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
            {STATUS_FILTERS.map(s => (
              <option key={s} value={s}>{s ? s.replace(/_/g, ' ') : 'Todos los estados'}</option>
            ))}
          </select>
          <Button size="sm" variant="secondary" disabled={!warehouseId} loading={nextMut.isPending}
            onClick={() => nextMut.mutate()} title={!warehouseId ? 'Selecciona una bodega' : 'Interleaving'}>
            <Zap className="h-4 w-4" /> Siguiente tarea
          </Button>
        </div>
        <Button size="sm" disabled={!warehouseId} onClick={() => setOpen(true)}
          title={!warehouseId ? 'Selecciona una bodega' : ''}>
          <Plus className="h-4 w-4" /> Nueva Tarea
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Actividad</Th><Th>Cantidad</Th><Th>Zona</Th><Th>Estado</Th>
              <Th>Prioridad</Th><Th>Desempeño</Th><Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 7 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-14" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={7} message="No hay tareas de labor" />
            ) : (
              data.items.map(t => (
                <Tr key={t.id}>
                  <Td className="capitalize font-medium text-gray-900">{t.activity_type.replace(/_/g, ' ')}</Td>
                  <Td>{fmt.number(t.quantity)} {t.uom}</Td>
                  <Td className="text-xs text-gray-500">{t.zone ?? '—'}</Td>
                  <Td><Badge status={t.status} /></Td>
                  <Td className="text-center">
                    <span className={t.priority <= 3 ? 'text-red-600 font-semibold' : 'text-gray-600'}>{t.priority}</span>
                  </Td>
                  <Td className={t.performance_pct != null ? (t.performance_pct >= 100 ? 'text-green-600' : 'text-orange-600') : 'text-gray-400'}>
                    {fmt.pct(t.performance_pct)}
                  </Td>
                  <Td>
                    <div className="flex gap-2">
                      {t.status === 'pending' && (
                        <button onClick={() => assignMut.mutate(t.id)} title="Asignarme"
                          className="text-blue-600 hover:text-blue-800 transition-colors">
                          <UserPlus className="h-4 w-4" />
                        </button>
                      )}
                      {(t.status === 'pending' || t.status === 'assigned') && (
                        <button onClick={() => startMut.mutate(t.id)} title="Iniciar"
                          className="text-indigo-600 hover:text-indigo-800 transition-colors">
                          <PlayCircle className="h-4 w-4" />
                        </button>
                      )}
                      {t.status === 'in_progress' && (
                        <Button size="sm" variant="secondary" onClick={() => completeMut.mutate(t.id)}>
                          Completar
                        </Button>
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

      <Modal open={open} onClose={() => setOpen(false)} title="Nueva tarea de labor"
        description="Se encola como 'pending' si no se asigna un operario."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={Number(quantity) <= 0} loading={createMut.isPending}
              onClick={() => createMut.mutate()}>Crear tarea</Button>
          </>
        }>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Actividad</label>
              <select value={activityType} onChange={e => setActivityType(e.target.value as LaborActivityType)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {ACTIVITY_TYPES.map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <Input label="Cantidad" type="number" min={1} value={quantity}
              onChange={e => setQuantity(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Zona (opcional)" value={zone} onChange={e => setZone(e.target.value)}
              placeholder="Ej. A01" />
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Prioridad</label>
              <select value={priority} onChange={e => setPriority(Number(e.target.value))}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {Array.from({ length: 9 }, (_, i) => i + 1).map(p => (
                  <option key={p} value={p}>{p}{p === 1 ? ' (urgente)' : ''}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Estándares ───────────────────────────────────────────
function StandardsTab({ warehouseId }: { warehouseId: string }) {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['labor-standards'],
    queryFn: () => laborApi.getStandards({ page_size: 100 }),
  })

  const [activityType, setActivityType] = useState<LaborActivityType>('pick')
  const [uom, setUom] = useState('unit')
  const [fixedMinutes, setFixedMinutes] = useState('0')
  const [perUnitMinutes, setPerUnitMinutes] = useState('0')
  const [description, setDescription] = useState('')
  const resetForm = () => {
    setActivityType('pick'); setUom('unit'); setFixedMinutes('0'); setPerUnitMinutes('0'); setDescription('')
  }

  const createMut = useMutation({
    mutationFn: () => laborApi.createStandard({
      activity_type: activityType,
      warehouse_id: warehouseId || undefined,
      uom, fixed_minutes: Number(fixedMinutes), std_minutes_per_unit: Number(perUnitMinutes),
      description: description || undefined,
    }),
    onSuccess: () => {
      toast.success('Estándar de labor creado')
      setOpen(false); resetForm()
      qc.invalidateQueries({ queryKey: ['labor-standards'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Error al crear el estándar'),
  })

  const toggleActiveMut = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      laborApi.updateStandard(id, { is_active }),
    onSuccess: () => {
      toast.success('Estándar actualizado')
      qc.invalidateQueries({ queryKey: ['labor-standards'] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {data?.total ?? 0} estándares · tiempo esperado = fijo + (por unidad × cantidad)
        </p>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Nuevo Estándar
        </Button>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Actividad</Th><Th>Bodega</Th><Th>UOM</Th><Th>Min. Fijo</Th>
              <Th>Min./Unidad</Th><Th>Descripción</Th><Th>Estado</Th><Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              <Tr><Td colSpan={8}><div className="h-4 bg-gray-100 rounded animate-pulse" /></Td></Tr>
            ) : !data?.items.length ? (
              <EmptyRow cols={8} message="No hay estándares configurados" />
            ) : (
              data.items.map(s => (
                <Tr key={s.id}>
                  <Td className="capitalize font-medium text-gray-900">{s.activity_type.replace(/_/g, ' ')}</Td>
                  <Td className="text-xs text-gray-500">{s.warehouse_id ? s.warehouse_id.slice(0, 8) : <span className="italic">Global</span>}</Td>
                  <Td>{s.uom}</Td>
                  <Td>{fmt.number(s.fixed_minutes)}</Td>
                  <Td>{fmt.number(s.std_minutes_per_unit)}</Td>
                  <Td className="text-xs text-gray-500 line-clamp-1">{s.description ?? '—'}</Td>
                  <Td>
                    <Badge status={s.is_active ? 'active' : 'inactive'} />
                  </Td>
                  <Td>
                    <button onClick={() => toggleActiveMut.mutate({ id: s.id, is_active: !s.is_active })}
                      className="text-xs text-primary-700 hover:underline">
                      {s.is_active ? 'Desactivar' : 'Activar'}
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title="Nuevo estándar de labor"
        description="Si no seleccionas bodega, aplica globalmente al tenant."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" loading={createMut.isPending} onClick={() => createMut.mutate()}>
              Crear estándar
            </Button>
          </>
        }>
        <div className="space-y-4">
          <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2 text-xs text-gray-500 flex items-center gap-2">
            <ListChecks className="h-3.5 w-3.5" />
            {warehouseId ? 'Se creará para la bodega seleccionada arriba.' : 'Se creará como estándar GLOBAL (sin bodega seleccionada).'}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Actividad</label>
              <select value={activityType} onChange={e => setActivityType(e.target.value as LaborActivityType)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {ACTIVITY_TYPES.map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <Input label="UOM" value={uom} onChange={e => setUom(e.target.value)} placeholder="unit | line | case | pallet" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Minutos fijos" type="number" min={0} step="0.1" value={fixedMinutes}
              onChange={e => setFixedMinutes(e.target.value)} />
            <Input label="Minutos por unidad" type="number" min={0} step="0.01" value={perUnitMinutes}
              onChange={e => setPerUnitMinutes(e.target.value)} />
          </div>
          <Input label="Descripción (opcional)" value={description} onChange={e => setDescription(e.target.value)} />
        </div>
      </Modal>
    </div>
  )
}
