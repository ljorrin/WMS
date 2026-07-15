import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play, CheckCircle2, XCircle, Gauge, ListChecks, Settings2,
  TrendingDown,
} from 'lucide-react'
import { slottingApi, warehouseApi } from '@/api/endpoints'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { KpiCard } from '@/components/ui/KpiCard'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const STATUS_FILTERS = ['', 'pending', 'applied', 'rejected', 'expired']
const ABC_FILTERS = ['', 'A', 'B', 'C']

type Tab = 'dashboard' | 'policy' | 'recommendations'

export function SlottingPage() {
  const [tab, setTab] = useState<Tab>('dashboard')
  const [warehouseId, setWarehouseId] = useState('')

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  useEffect(() => {
    if (!warehouseId && warehouses?.items.length) setWarehouseId(warehouses.items[0].id)
  }, [warehouses, warehouseId])

  const tabs: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: Gauge },
    { id: 'policy', label: 'Política', icon: Settings2 },
    { id: 'recommendations', label: 'Recomendaciones', icon: ListChecks },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Slotting Dinámico</h1>
          <p className="text-sm text-gray-500 mt-1">
            Clasificación ABC por rotación y re-slotting continuo hacia la zona dorada de picking.
          </p>
        </div>
        <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
          className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
          <option value="">Seleccionar bodega…</option>
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

      {!warehouseId ? (
        <p className="text-sm text-gray-400 py-10 text-center">Selecciona una bodega para continuar.</p>
      ) : (
        <>
          {tab === 'dashboard' && <DashboardTab warehouseId={warehouseId} />}
          {tab === 'policy' && <PolicyTab warehouseId={warehouseId} />}
          {tab === 'recommendations' && <RecommendationsTab warehouseId={warehouseId} />}
        </>
      )}
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────
function DashboardTab({ warehouseId }: { warehouseId: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['slotting-dashboard', warehouseId],
    queryFn: () => slottingApi.getDashboard(warehouseId),
  })

  const analyzeMut = useMutation({
    mutationFn: () => slottingApi.analyze(warehouseId),
    onSuccess: (res) => {
      toast.success(`Análisis completo: ${res.products_analyzed} productos, ${res.recommendations_created} recomendaciones nuevas`)
      qc.invalidateQueries({ queryKey: ['slotting-dashboard'] })
      qc.invalidateQueries({ queryKey: ['slotting-recommendations'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Error al ejecutar el análisis'),
  })

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button size="sm" loading={analyzeMut.isPending} onClick={() => analyzeMut.mutate()}>
          <Play className="h-4 w-4" /> Ejecutar Análisis ABC
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard title="Recomendaciones Pendientes" value={data?.pending ?? 0}
          icon={ListChecks} loading={isLoading} alert={(data?.pending ?? 0) > 0} />
        <KpiCard title="Aplicadas" value={data?.applied ?? 0} icon={CheckCircle2} loading={isLoading} />
        <KpiCard title="Rechazadas" value={data?.rejected ?? 0} icon={XCircle} loading={isLoading} />
        <KpiCard title="Ahorro Estimado de Recorrido" value={fmt.number(data?.estimated_travel_savings)}
          subtitle="Proxy: posiciones × frecuencia de picks" icon={TrendingDown} loading={isLoading} />
      </div>

      <Card>
        <CardHeader><CardTitle>Pendientes por Clase ABC</CardTitle></CardHeader>
        <div className="flex gap-4">
          {['A', 'B', 'C'].map(cls => (
            <div key={cls} className="flex-1 rounded-lg border border-gray-100 bg-gray-50 p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">{data?.pending_by_class?.[cls] ?? 0}</p>
              <p className="text-xs text-gray-500 mt-1">Clase {cls}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ─── Política ─────────────────────────────────────────────
function PolicyTab({ warehouseId }: { warehouseId: string }) {
  const qc = useQueryClient()
  const { data: policies } = useQuery({
    queryKey: ['slotting-policies'],
    queryFn: () => slottingApi.getPolicies(),
  })

  const existing = policies?.items.find(p => p.warehouse_id === warehouseId)

  const [strategy, setStrategy] = useState('velocity_abc')
  const [windowDays, setWindowDays] = useState('90')
  const [thresholdA, setThresholdA] = useState('0.80')
  const [thresholdB, setThresholdB] = useState('0.95')
  const [goldenZone, setGoldenZone] = useState('')
  const [bulkZone, setBulkZone] = useState('')

  useEffect(() => {
    if (existing) {
      setStrategy(existing.strategy)
      setWindowDays(String(existing.velocity_window_days))
      setThresholdA(String(existing.abc_a_threshold))
      setThresholdB(String(existing.abc_b_threshold))
      setGoldenZone(existing.golden_zone_code ?? '')
      setBulkZone(existing.bulk_zone_code ?? '')
    }
  }, [existing?.id])

  const saveMut = useMutation({
    mutationFn: () => slottingApi.upsertPolicy({
      warehouse_id: warehouseId,
      strategy,
      velocity_window_days: Number(windowDays),
      abc_a_threshold: Number(thresholdA),
      abc_b_threshold: Number(thresholdB),
      golden_zone_code: goldenZone || undefined,
      bulk_zone_code: bulkZone || undefined,
      is_active: true,
    }),
    onSuccess: () => {
      toast.success('Política de slotting guardada')
      qc.invalidateQueries({ queryKey: ['slotting-policies'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Error al guardar la política'),
  })

  return (
    <Card className="max-w-2xl">
      <CardHeader><CardTitle>Política de la bodega seleccionada</CardTitle></CardHeader>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Ventana de velocidad (días)" type="number" min={7} max={730} value={windowDays}
            onChange={e => setWindowDays(e.target.value)} />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Estrategia</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              <option value="velocity_abc">Velocidad ABC</option>
              <option value="manual">Manual</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Umbral clase A (0-1)" type="number" step="0.01" min={0} max={1} value={thresholdA}
            onChange={e => setThresholdA(e.target.value)} />
          <Input label="Umbral clase B (0-1)" type="number" step="0.01" min={0} max={1} value={thresholdB}
            onChange={e => setThresholdB(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Zona dorada (picking)" value={goldenZone} onChange={e => setGoldenZone(e.target.value)}
            placeholder="Ej. A01" />
          <Input label="Zona de bulk / reserva" value={bulkZone} onChange={e => setBulkZone(e.target.value)}
            placeholder="Ej. B99" />
        </div>
        <div className="flex justify-end">
          <Button size="sm" loading={saveMut.isPending} onClick={() => saveMut.mutate()}>
            Guardar política
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ─── Recomendaciones ──────────────────────────────────────
function RecommendationsTab({ warehouseId }: { warehouseId: string }) {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('pending')
  const [abcClass, setAbcClass] = useState('')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['slotting-recommendations', warehouseId, page, status, abcClass],
    queryFn: () => slottingApi.getRecommendations({
      warehouse_id: warehouseId, page, page_size: PAGE_SIZE,
      ...(status ? { status } : {}), ...(abcClass ? { abc_class: abcClass } : {}),
    }),
    placeholderData: prev => prev,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['slotting-recommendations'] })
  const applyMut = useMutation({
    mutationFn: (id: string) => slottingApi.applyRecommendation(id),
    onSuccess: () => { toast.success('Recomendación aplicada'); invalidate() },
  })
  const rejectMut = useMutation({
    mutationFn: (id: string) => slottingApi.rejectRecommendation(id),
    onSuccess: () => { toast.success('Recomendación rechazada'); invalidate() },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
          {STATUS_FILTERS.map(s => (
            <option key={s} value={s}>{s ? s.replace(/_/g, ' ') : 'Todos los estados'}</option>
          ))}
        </select>
        <select value={abcClass} onChange={e => { setAbcClass(e.target.value); setPage(1) }}
          className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
          {ABC_FILTERS.map(c => <option key={c} value={c}>{c ? `Clase ${c}` : 'Todas las clases'}</option>)}
        </select>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Producto</Th><Th>Clase</Th><Th>Velocidad</Th>
              <Th>De</Th><Th>A</Th><Th>Motivo</Th><Th>Ahorro</Th><Th>Estado</Th><Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 9 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-14" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={9} message="No hay recomendaciones — ejecuta el análisis en el Dashboard" />
            ) : (
              data.items.map(r => (
                <Tr key={r.id}>
                  <Td className="font-mono text-xs">{r.product_name ?? r.product_id.slice(0, 8)}</Td>
                  <Td><span className="font-bold text-primary-700">{r.abc_class ?? '—'}</span></Td>
                  <Td>{fmt.number(r.velocity_score)}</Td>
                  <Td className="text-xs text-gray-500">{r.current_zone_code ?? '—'}</Td>
                  <Td className="text-xs font-semibold text-primary-700">{r.recommended_zone_code ?? '—'}</Td>
                  <Td className="text-xs text-gray-500 max-w-xs line-clamp-2" title={r.reason ?? ''}>{r.reason ?? '—'}</Td>
                  <Td>{fmt.number(r.score_delta)}</Td>
                  <Td><Badge status={r.status} /></Td>
                  <Td>
                    {r.status === 'pending' && (
                      <div className="flex gap-2">
                        <button onClick={() => applyMut.mutate(r.id)} title="Aplicar"
                          className="text-green-600 hover:text-green-800 transition-colors">
                          <CheckCircle2 className="h-4 w-4" />
                        </button>
                        <button onClick={() => rejectMut.mutate(r.id)} title="Rechazar"
                          className="text-red-600 hover:text-red-800 transition-colors">
                          <XCircle className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>
    </div>
  )
}
