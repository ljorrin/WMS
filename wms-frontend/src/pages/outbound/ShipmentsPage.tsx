import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Truck, PackageCheck, Ship, Plane } from 'lucide-react'
import { outboundApi } from '@/api/endpoints'
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
              <Th>Orden / Cliente</Th>
              <Th>Estado</Th>
              <Th>Transportista</Th>
              <Th>Tracking</Th>
              <Th>Bultos</Th>
              <Th>Despacho</Th>
              <Th>Entrega</Th>
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
              <EmptyRow cols={8} message="No hay envíos registrados" />
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
                  <Td>
                    <div className="flex gap-1">
                      {(s.status === 'pending' || s.status === 'ready') && (
                        <Button size="sm" variant="secondary" onClick={() => openDispatch(s)}>
                          Despachar
                        </Button>
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
