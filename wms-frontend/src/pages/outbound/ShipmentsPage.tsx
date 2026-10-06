import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Truck, PackageCheck, Ship, Plane, Send, CheckCircle2, AlertTriangle } from 'lucide-react'
import { outboundApi, integrationsApi } from '@/api/endpoints'
import { ShipmentCreateModal } from './ShipmentCreateModal'
import { TmsSendModal, type TmsSendTarget } from './TmsSendModal'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { Shipment } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const STATUS_FILTERS = ['', 'pending', 'ready', 'in_transit', 'delivered', 'failed', 'returned']

// Convierte un valor datetime-local a ISO 8601; default = ahora
const nowLocal = () => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

export function ShipmentsPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [creating, setCreating] = useState(false)
  const [mode, setMode] = useState<'dispatch' | 'deliver' | null>(null)
  const [target, setTarget] = useState<Shipment | null>(null)
  const qc = useQueryClient()

  // Form dispatch
  const [actualPickup, setActualPickup] = useState(nowLocal())
  const [tracking, setTracking] = useState('')
  const [vehiclePlate, setVehiclePlate] = useState('')
  const [driverName, setDriverName] = useState('')
  // Form deliver
  const [actualDelivery, setActualDelivery] = useState(nowLocal())
  const [deliveredTo, setDeliveredTo] = useState('')
  const [photoUrl, setPhotoUrl] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['shipments', page, status],
    queryFn: () => outboundApi.getShipments({
      page, page_size: PAGE_SIZE, ...(status ? { status } : {}),
    }),
    placeholderData: prev => prev,
  })

  // Integración TMS: el botón solo aparece si el backend tiene TMS_* configurado
  const { data: integrations } = useQuery({
    queryKey: ['integrations-status'],
    queryFn: integrationsApi.getStatus,
    staleTime: 5 * 60_000,
  })
  const tmsEnabled = !!integrations?.tms?.configured

  // Envío al TMS: abre el modal de confirmación (vista previa → envío → resultado)
  const [tmsTarget, setTmsTarget] = useState<TmsSendTarget | null>(null)

  const dispatchMut = useMutation({
    mutationFn: () => outboundApi.dispatchShipment(target!.id, {
      actual_pickup: new Date(actualPickup).toISOString(),
      tracking_number: tracking || undefined,
      vehicle_plate: vehiclePlate || undefined,
      driver_name: driverName || undefined,
    }),
    onSuccess: () => {
      toast.success('Envío despachado — en tránsito')
      closeModal()
      qc.invalidateQueries({ queryKey: ['shipments'] })
    },
  })

  const deliverMut = useMutation({
    mutationFn: () => outboundApi.deliverShipment(target!.id, {
      actual_delivery: new Date(actualDelivery).toISOString(),
      delivered_to_name: deliveredTo,
      delivery_photo_url: photoUrl || undefined,
    }),
    onSuccess: () => {
      toast.success('Envío marcado como entregado')
      closeModal()
      qc.invalidateQueries({ queryKey: ['shipments'] })
    },
  })

  const closeModal = () => {
    setMode(null); setTarget(null)
    setActualPickup(nowLocal()); setTracking(''); setVehiclePlate(''); setDriverName('')
    setActualDelivery(nowLocal()); setDeliveredTo(''); setPhotoUrl('')
  }

  const openDispatch = (s: Shipment) => {
    setTarget(s); setMode('dispatch')
    setTracking(s.tracking_number ?? ''); setVehiclePlate(s.vehicle_plate ?? ''); setDriverName(s.driver_name ?? '')
  }
  const openDeliver = (s: Shipment) => {
    setTarget(s); setMode('deliver'); setDeliveredTo(s.delivered_to_name ?? '')
  }

  const carrierIcon = (s: Shipment) =>
    s.is_export ? (s.carrier_type === 'air' ? <Plane className="h-3 w-3" /> : <Ship className="h-3 w-3" />)
      : <Truck className="h-3 w-3" />

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Envíos</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} envíos</p>
        </div>
        <div className="flex gap-2">
          <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
            {STATUS_FILTERS.map(s => (
              <option key={s} value={s}>{s ? s.replace(/_/g, ' ') : 'Todos los estados'}</option>
            ))}
          </select>
          {tmsEnabled && (
            <Button size="sm" variant="secondary" onClick={() => setTmsTarget({ all: true })}
              title="Envía al TMS todos los envíos pendientes que aún no se han enviado">
              <Send className="h-4 w-4" /> Enviar pendientes al TMS
            </Button>
          )}
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" /> Nuevo Envío
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Orden / Cliente</Th>
              <Th>Estado</Th>
              <Th>Transportista</Th>
              <Th>Tracking</Th>
              <Th>Bultos</Th>
              <Th>Despacho</Th>
              <Th>Entrega</Th>
              <Th>TMS</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 10 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-16" /></Td>
                  ))}
                </Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={10} message="No hay envíos registrados" />
            ) : (
              data.items.map(s => (
                <Tr key={s.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{s.shipment_number}</span></Td>
                  <Td>
                    <div className="flex flex-col">
                      <span className="font-semibold text-gray-900">{s.so_number ?? '—'}</span>
                      <span className="text-gray-500 text-xs">{s.customer_name ?? '—'}</span>
                    </div>
                  </Td>
                  <Td><Badge status={s.status} /></Td>
                  <Td>
                    <span className="inline-flex items-center gap-1 text-xs text-gray-600">
                      {carrierIcon(s)} {s.carrier_name ?? s.carrier_type ?? '—'}
                      {s.is_export && <span className="ml-1 text-[10px] font-semibold text-amber-600">EXPORT</span>}
                    </span>
                  </Td>
                  <Td className="text-xs font-mono text-gray-500">{s.tracking_number ?? '—'}</Td>
                  <Td className="text-center">{s.total_boxes}</Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(s.actual_pickup)}</Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(s.actual_delivery)}</Td>
                  <Td className="text-xs">
                    {s.tms_sent_at ? (
                      <span className="inline-flex items-center gap-1 text-green-700"
                        title={`Enviado ${fmt.datetime(s.tms_sent_at)}${s.tms_order_id ? ` · Orden TMS ${s.tms_order_id}` : ''}`}>
                        <CheckCircle2 className="h-3.5 w-3.5" /> En TMS
                      </span>
                    ) : s.tms_last_error ? (
                      <span className="inline-flex items-center gap-1 text-red-600" title={s.tms_last_error}>
                        <AlertTriangle className="h-3.5 w-3.5" /> Error
                      </span>
                    ) : <span className="text-gray-300">—</span>}
                  </Td>
                  <Td>
                    <div className="flex gap-1">
                      {s.status === 'pending' && tmsEnabled && !s.tms_sent_at && (
                        <Button size="sm"
                          onClick={() => setTmsTarget({ ids: [s.id] })}
                          title="Enviar la orden al TMS para que planifique y despache la ruta">
                          <Send className="h-4 w-4" /> TMS
                        </Button>
                      )}
                      {(s.status === 'pending' || s.status === 'ready') && !s.tms_sent_at && (
                        <Button size="sm" variant="secondary" onClick={() => openDispatch(s)}
                          title="Despacho manual, sin TMS">
                          Despachar
                        </Button>
                      )}
                      {(s.status === 'pending' || s.status === 'ready') && s.tms_sent_at && (
                        <span className="text-xs text-gray-500 self-center">Lo despacha el TMS</span>
                      )}
                      {s.status === 'in_transit' && (
                        <Button size="sm" variant="secondary" onClick={() => openDeliver(s)}>
                          Entregar
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

      <ShipmentCreateModal open={creating} onClose={() => setCreating(false)} />

      <TmsSendModal target={tmsTarget} onClose={() => setTmsTarget(null)} />

      {/* Despacho */}
      <Modal
        open={mode === 'dispatch'}
        onClose={closeModal}
        title={`Despachar ${target?.shipment_number ?? ''}`}
        description="Confirma la salida del vehículo y los datos de transporte."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={closeModal}>Cancelar</Button>
            <Button size="sm" disabled={!actualPickup} loading={dispatchMut.isPending}
              onClick={() => dispatchMut.mutate()}>
              <Truck className="h-4 w-4" /> Despachar
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Hora de salida</label>
            <input type="datetime-local" value={actualPickup} onChange={e => setActualPickup(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm" />
          </div>
          <Input label="Número de tracking" value={tracking}
            onChange={e => setTracking(e.target.value)} placeholder="Guía / tracking" />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Placa del vehículo" value={vehiclePlate}
              onChange={e => setVehiclePlate(e.target.value)} placeholder="Ej: 700123" />
            <Input label="Conductor" value={driverName}
              onChange={e => setDriverName(e.target.value)} placeholder="Nombre" />
          </div>
        </div>
      </Modal>

      {/* Entrega */}
      <Modal
        open={mode === 'deliver'}
        onClose={closeModal}
        title={`Confirmar entrega ${target?.shipment_number ?? ''}`}
        description="Registra la prueba de entrega (POD)."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={closeModal}>Cancelar</Button>
            <Button size="sm" disabled={!actualDelivery || deliveredTo.length < 2} loading={deliverMut.isPending}
              onClick={() => deliverMut.mutate()}>
              <PackageCheck className="h-4 w-4" /> Entregado
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Hora de entrega</label>
            <input type="datetime-local" value={actualDelivery} onChange={e => setActualDelivery(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm" />
          </div>
          <Input label="Recibido por" value={deliveredTo}
            onChange={e => setDeliveredTo(e.target.value)} placeholder="Nombre de quien recibe" />
          <Input label="URL de foto de entrega" value={photoUrl}
            onChange={e => setPhotoUrl(e.target.value)} placeholder="Opcional" />
        </div>
      </Modal>
    </div>
  )
}
