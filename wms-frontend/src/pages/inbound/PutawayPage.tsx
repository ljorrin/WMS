import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlayCircle, MapPin, ArrowRight } from 'lucide-react'
import { inboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { PutawayTask } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const STATUS_FILTERS = ['', 'pending', 'in_progress', 'completed', 'cancelled']

export function PutawayPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [target, setTarget] = useState<PutawayTask | null>(null)
  const [actualLocation, setActualLocation] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['putaway', page, status],
    queryFn: () => inboundApi.getPutawayTasks({
      page, page_size: PAGE_SIZE, ...(status ? { status } : {}),
    }),
    placeholderData: prev => prev,
  })

  const startMut = useMutation({
    mutationFn: (id: string) => inboundApi.startPutaway(id),
    onSuccess: () => {
      toast.success('Tarea de putaway iniciada')
      qc.invalidateQueries({ queryKey: ['putaway'] })
    },
  })

  const completeMut = useMutation({
    mutationFn: () => inboundApi.completePutaway(
      target!.id, actualLocation, overrideReason || undefined,
    ),
    onSuccess: () => {
      toast.success('Putaway completado — stock ubicado')
      setTarget(null); setActualLocation(''); setOverrideReason('')
      qc.invalidateQueries({ queryKey: ['putaway'] })
    },
  })

  // Si la ubicación real difiere de la sugerida, el motivo de override es obligatorio
  const isOverride = !!target?.suggested_location_id &&
    actualLocation.length > 0 &&
    actualLocation !== target.suggested_location_code &&
    actualLocation !== target.suggested_location_id
  const completeValid = actualLocation.length > 0 && (!isOverride || overrideReason.length >= 3)

  const openComplete = (t: PutawayTask) => {
    setTarget(t)
    setActualLocation(t.suggested_location_code ?? t.suggested_location_id ?? '')
    setOverrideReason('')
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Putaway (Ubicación)</h1>
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
              <Th>Producto</Th>
              <Th>Cantidad</Th>
              <Th>Origen</Th>
              <Th>Sugerida</Th>
              <Th>Estado</Th>
              <Th>Prioridad</Th>
              <Th>Ciclo</Th>
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
              <EmptyRow cols={8} message="No hay tareas de putaway" />
            ) : (
              data.items.map(t => (
                <Tr key={t.id}>
                  <Td>
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-900 line-clamp-1" title={t.product_name ?? ''}>
                        {t.product_name ?? 'Producto Desconocido'}
                      </span>
                      <span className="text-gray-500 text-xs font-mono">{t.product_id}</span>
                    </div>
                  </Td>
                  <Td className="font-medium">{fmt.number(t.quantity)}</Td>
                  <Td className="text-xs text-gray-500">
                    <span className="inline-flex items-center gap-1" title={t.from_location_id ?? ''}>
                      <MapPin className="h-3 w-3" /> {t.from_location_code ?? t.from_location_id?.slice(0, 8) ?? '—'}
                    </span>
                  </Td>
                  <Td className="text-xs">
                    {t.suggested_location_id ? (
                      <span className="inline-flex items-center gap-1 text-primary-700 font-semibold" title={t.suggested_location_id}>
                        <ArrowRight className="h-3 w-3" /> {t.suggested_location_code ?? t.suggested_location_id.slice(0, 8)}
                      </span>
                    ) : <span className="text-gray-400">—</span>}
                  </Td>
                  <Td><Badge status={t.status} /></Td>
                  <Td className="text-center">
                    <span className={t.priority <= 3 ? 'text-red-600 font-semibold' : 'text-gray-600'}>
                      {t.priority}
                    </span>
                  </Td>
                  <Td className="text-xs text-gray-400">{fmt.seconds(t.cycle_time_seconds)}</Td>
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
        title="Completar putaway"
        description="Confirma la ubicación física donde se almacenó el material."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setTarget(null)}>Cancelar</Button>
            <Button size="sm" disabled={!completeValid} loading={completeMut.isPending}
              onClick={() => completeMut.mutate()}>Confirmar ubicación</Button>
          </>
        }
      >
        <div className="space-y-4">
          {target?.suggested_location_id && (
            <div className="rounded-lg bg-primary-50 border border-primary-100 px-3 py-2 text-sm text-primary-800">
              Ubicación sugerida: <span className="font-mono font-semibold" title={target.suggested_location_id}>{target.suggested_location_code ?? target.suggested_location_id}</span>
            </div>
          )}
          <Input label="Ubicación real (Código o ID)" value={actualLocation}
            onChange={e => setActualLocation(e.target.value)}
            placeholder="Ej. A-01-B-05 o UUID de la ubicación" />
          {isOverride && (
            <Input label="Motivo de cambio de ubicación" value={overrideReason}
              onChange={e => setOverrideReason(e.target.value)}
              placeholder="Obligatorio: difiere de la sugerida (mín. 3 caracteres)"
              error={overrideReason.length > 0 && overrideReason.length < 3 ? 'Mínimo 3 caracteres' : undefined} />
          )}
        </div>
      </Modal>
    </div>
  )
}
