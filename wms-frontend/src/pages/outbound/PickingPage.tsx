import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlayCircle, ScanLine, MapPin } from 'lucide-react'
import { outboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { PickingTask } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const STATUS_FILTERS = ['', 'pending', 'in_progress', 'completed', 'short_picked', 'cancelled']

export function PickingPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [target, setTarget] = useState<PickingTask | null>(null)
  const [qtyPicked, setQtyPicked] = useState('')
  const [ssccScanned, setSsccScanned] = useState('')
  const [gtinScanned, setGtinScanned] = useState('')
  const [shortReason, setShortReason] = useState('')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['picking', page, status],
    queryFn: () => outboundApi.getPickingTasks({
      page, page_size: PAGE_SIZE, ...(status ? { status } : {}),
    }),
    placeholderData: prev => prev,
  })

  const startMut = useMutation({
    mutationFn: (id: string) => outboundApi.startPick(id),
    onSuccess: () => {
      toast.success('Picking iniciado')
      qc.invalidateQueries({ queryKey: ['picking'] })
    },
  })

  const completeMut = useMutation({
    mutationFn: () => outboundApi.completePick(target!.id, {
      quantity_picked: Number(qtyPicked),
      sscc_scanned: ssccScanned || undefined,
      gtin_scanned: gtinScanned || undefined,
      short_reason: shortReason || undefined,
    }),
    onSuccess: () => {
      toast.success('Tarea de picking completada')
      setTarget(null); setQtyPicked(''); setSsccScanned(''); setGtinScanned(''); setShortReason('')
      qc.invalidateQueries({ queryKey: ['picking'] })
    },
  })

  const openComplete = (t: PickingTask) => {
    setTarget(t)
    setQtyPicked(String(t.quantity_requested))
    setSsccScanned(''); setGtinScanned(''); setShortReason('')
  }

  const isShort = !!target && qtyPicked !== '' && Number(qtyPicked) < target.quantity_requested
  const completeValid = qtyPicked !== '' && Number(qtyPicked) >= 0 &&
    (!isShort || shortReason.length >= 3)

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Picking</h1>
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
              <Th>Ubicación</Th>
              <Th>Solicitado</Th>
              <Th>Pickeado</Th>
              <Th>Faltante</Th>
              <Th>Estado</Th>
              <Th>Prioridad</Th>
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
              <EmptyRow cols={8} message="No hay tareas de picking" />
            ) : (
              data.items.map(t => (
                <Tr key={t.id}>
                  <Td>
                    <div className="flex flex-col">
                      <span className="font-semibold text-gray-900">{t.product_name ?? 'Producto Desconocido'}</span>
                      <span className="text-gray-400 text-xs font-mono">{t.product_id.slice(0, 8)}</span>
                    </div>
                  </Td>
                  <Td className="text-xs text-gray-500">
                    <span className="inline-flex items-center gap-1" title={t.from_location_id}>
                      <MapPin className="h-3 w-3" /> {t.from_location_code ?? t.from_location_id?.slice(0, 8) ?? '—'}
                    </span>
                  </Td>
                  <Td className="font-medium">{fmt.number(t.quantity_requested)}</Td>
                  <Td className="text-green-700 font-medium">{fmt.number(t.quantity_picked)}</Td>
                  <Td className={t.quantity_short > 0 ? 'text-orange-600 font-medium' : 'text-gray-400'}>
                    {fmt.number(t.quantity_short)}
                  </Td>
                  <Td><Badge status={t.status} /></Td>
                  <Td className="text-center">
                    <span className={t.priority <= 3 ? 'text-red-600 font-semibold' : 'text-gray-600'}>
                      {t.priority}
                    </span>
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
        title="Completar picking"
        description="Registra la cantidad pickeada y escaneos de validación."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setTarget(null)}>Cancelar</Button>
            <Button size="sm" disabled={!completeValid} loading={completeMut.isPending}
              onClick={() => completeMut.mutate()}>Confirmar picking</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2 text-sm text-gray-600">
            Cantidad solicitada: <span className="font-semibold text-gray-900">{fmt.number(target?.quantity_requested)}</span>
          </div>
          <Input label="Cantidad pickeada" type="number" value={qtyPicked}
            onChange={e => setQtyPicked(e.target.value)} placeholder="0" />
          <div className="grid grid-cols-2 gap-3">
            <Input label="SSCC escaneado" value={ssccScanned}
              onChange={e => setSsccScanned(e.target.value)} placeholder="Opcional" />
            <Input label="GTIN escaneado" value={gtinScanned}
              onChange={e => setGtinScanned(e.target.value)} placeholder="Opcional" />
          </div>
          {isShort && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 rounded-lg bg-orange-50 border border-orange-200 px-3 py-2 text-sm text-orange-700">
                <ScanLine className="h-4 w-4 shrink-0" />
                Picking parcial (short) — el motivo es obligatorio.
              </div>
              <Input label="Motivo del faltante" value={shortReason}
                onChange={e => setShortReason(e.target.value)}
                placeholder="Ej: stock insuficiente en ubicación"
                error={shortReason.length > 0 && shortReason.length < 3 ? 'Mínimo 3 caracteres' : undefined} />
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
