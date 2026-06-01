import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlayCircle, Package, Printer } from 'lucide-react'
import { outboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { PackTask } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const STATUS_FILTERS = ['', 'pending', 'in_progress', 'completed', 'cancelled']
const BOX_TYPES = ['carton_s', 'carton_m', 'carton_l', 'pallet', 'envelope', 'custom']

export function PackingPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [target, setTarget] = useState<PackTask | null>(null)
  const [boxType, setBoxType] = useState('carton_m')
  const [boxCount, setBoxCount] = useState('1')
  const [weight, setWeight] = useState('')
  const [volume, setVolume] = useState('')
  const [sscc, setSscc] = useState('')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['packing', page, status],
    queryFn: () => outboundApi.getPackTasks({
      page, page_size: PAGE_SIZE, ...(status ? { status } : {}),
    }),
    placeholderData: prev => prev,
  })

  const startMut = useMutation({
    mutationFn: (id: string) => outboundApi.startPack(id),
    onSuccess: () => {
      toast.success('Empaque iniciado')
      qc.invalidateQueries({ queryKey: ['packing'] })
    },
  })

  const completeMut = useMutation({
    mutationFn: () => outboundApi.completePack(target!.id, {
      box_type: boxType,
      box_count: Number(boxCount),
      total_weight_kg: weight ? Number(weight) : undefined,
      total_volume_m3: volume ? Number(volume) : undefined,
      sscc: sscc || undefined,
    }),
    onSuccess: () => {
      toast.success('Empaque completado — listo para envío')
      setTarget(null); setBoxType('carton_m'); setBoxCount('1'); setWeight(''); setVolume(''); setSscc('')
      qc.invalidateQueries({ queryKey: ['packing'] })
    },
  })

  const openComplete = (t: PackTask) => {
    setTarget(t)
    setBoxType(t.box_type ?? 'carton_m')
    setBoxCount(String(t.box_count || 1))
    setWeight(t.total_weight_kg != null ? String(t.total_weight_kg) : '')
    setVolume(t.total_volume_m3 != null ? String(t.total_volume_m3) : '')
    setSscc(t.sscc ?? '')
  }

  const completeValid = boxType.length > 0 && Number(boxCount) >= 1

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Empaque (Packing)</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} tareas</p>
        </div>
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
          {STATUS_FILTERS.map(s => (
            <option key={s} value={s}>{s ? s.replace(/_/g, ' ') : 'Todos los estados'}</option>
          ))}
        </select>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Tipo caja</Th>
              <Th>Cajas</Th>
              <Th>Peso</Th>
              <Th>SSCC</Th>
              <Th>Etiquetas</Th>
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
              <EmptyRow cols={8} message="No hay tareas de empaque" />
            ) : (
              data.items.map(t => (
                <Tr key={t.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{t.pack_task_number}</span></Td>
                  <Td><Badge status={t.status} /></Td>
                  <Td className="text-xs text-gray-500 capitalize">{t.box_type?.replace(/_/g, ' ') ?? '—'}</Td>
                  <Td className="text-center">{t.box_count}</Td>
                  <Td>{t.total_weight_kg != null ? `${fmt.number(t.total_weight_kg)} kg` : '—'}</Td>
                  <Td className="text-xs font-mono text-gray-500">{t.sscc ?? '—'}</Td>
                  <Td>
                    <div className="flex gap-1">
                      <Printer className={t.label_printed ? 'h-4 w-4 text-green-600' : 'h-4 w-4 text-gray-300'} />
                      <Package className={t.packing_list_printed ? 'h-4 w-4 text-green-600' : 'h-4 w-4 text-gray-300'} />
                    </div>
                  </Td>
                  <Td>
                    <div className="flex gap-1">
                      {t.status === 'pending' && (
                        <button onClick={() => startMut.mutate(t.id)} title="Iniciar"
                          className="text-blue-600 hover:text-blue-800 transition-colors">
                          <PlayCircle className="h-4 w-4" />
                        </button>
                      )}
                      {t.status === 'in_progress' && (
                        <Button size="sm" variant="secondary" onClick={() => openComplete(t)}>
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

      <Modal
        open={!!target}
        onClose={() => setTarget(null)}
        title={`Completar empaque ${target?.pack_task_number ?? ''}`}
        description="Registra el detalle de cajas y peso del bulto final."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setTarget(null)}>Cancelar</Button>
            <Button size="sm" disabled={!completeValid} loading={completeMut.isPending}
              onClick={() => completeMut.mutate()}>Confirmar empaque</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Tipo de caja</label>
              <select value={boxType} onChange={e => setBoxType(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {BOX_TYPES.map(b => <option key={b} value={b}>{b.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <Input label="Número de cajas" type="number" value={boxCount}
              onChange={e => setBoxCount(e.target.value)} placeholder="1" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Peso total (kg)" type="number" value={weight}
              onChange={e => setWeight(e.target.value)} placeholder="Opcional" />
            <Input label="Volumen (m³)" type="number" value={volume}
              onChange={e => setVolume(e.target.value)} placeholder="Opcional" />
          </div>
          <Input label="SSCC del bulto" value={sscc}
            onChange={e => setSscc(e.target.value)} placeholder="Opcional — código de contenedor" />
        </div>
      </Modal>
    </div>
  )
}
