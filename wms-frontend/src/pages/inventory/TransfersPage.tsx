import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRightLeft, XCircle } from 'lucide-react'
import { inventoryApi, masterApi, warehouseApi } from '@/api/endpoints'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Combobox } from '@/components/ui/Combobox'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'
import type { Product, LocationLite } from '@/types'
import toast from 'react-hot-toast'

export function TransfersPage() {
  const qc = useQueryClient()

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const { data: reservations, isLoading } = useQuery({
    queryKey: ['reservations'],
    queryFn: () => inventoryApi.getReservations({ page_size: 50, is_active: true }),
  })

  // Formulario de transferencia
  const [warehouseId, setWarehouseId] = useState('')
  const [productId, setProductId] = useState('')
  const [productLabel, setProductLabel] = useState('')
  const [fromLocationId, setFromLocationId] = useState('')
  const [fromLocationLabel, setFromLocationLabel] = useState('')
  const [toLocationId, setToLocationId] = useState('')
  const [toLocationLabel, setToLocationLabel] = useState('')
  const [quantity, setQuantity] = useState('')

  const { data: recentTransfersData } = useQuery({
    queryKey: ['recent-transfers', warehouseId],
    queryFn: () => inventoryApi.getMovements({ 
      movement_type: 'transfer_out',
      ...(warehouseId ? { warehouse_id: warehouseId } : {}),
      page_size: 10 
    }),
  })

  const recentTransfers = recentTransfersData?.items.map((m: any) => ({
    id: m.id,
    productLabel: `${m.product_code || ''} — ${m.product_name || ''}`,
    fromLabel: m.from_location_code || 'N/A',
    toLabel: m.to_location_code || 'N/A',
    quantity: m.quantity,
    at: m.occurred_at
  })) || []

  const resetForm = () => {
    setProductId(''); setProductLabel('')
    setFromLocationId(''); setFromLocationLabel('')
    setToLocationId(''); setToLocationLabel('')
    setQuantity('')
  }

  const transferMut = useMutation({
    mutationFn: () => inventoryApi.transferStock({
      warehouse_id: warehouseId,
      product_id: productId,
      from_location_id: fromLocationId,
      to_location_id: toLocationId,
      quantity: Number(quantity),
    }),
    onSuccess: () => {
      toast.success('Transferencia realizada')
      resetForm()
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['recent-transfers'] })
    },
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => inventoryApi.cancelReservation(id),
    onSuccess: () => {
      toast.success('Reserva cancelada — stock liberado')
      qc.invalidateQueries({ queryKey: ['reservations'] })
    },
  })

  const formValid = warehouseId && productId && fromLocationId && toLocationId &&
    fromLocationId !== toLocationId && Number(quantity) > 0

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Transferencias y Reservas</h1>
        <p className="text-sm text-gray-500">Mover stock entre ubicaciones y gestionar reservas activas</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <ArrowRightLeft className="h-5 w-5 text-primary-600" /> Transferir stock
          </CardTitle>
        </CardHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Bodega</label>
            <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              <option value="">Seleccionar…</option>
              {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Producto</label>
            <Combobox<Product>
              placeholder="Buscar producto…"
              value={productId}
              displayLabel={productLabel}
              queryKey="products-transfer"
              fetcher={s => masterApi.getProducts({ search: s, page_size: 20, status: 'active' })}
              getKey={p => p.id}
              getLabel={p => `${p.sku} — ${p.name}`}
              onSelect={p => { setProductId(p.id); setProductLabel(`${p.sku} — ${p.name}`) }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Origen</label>
            <Combobox<LocationLite>
              placeholder="Ubicación origen…"
              value={fromLocationId}
              displayLabel={fromLocationLabel}
              queryKey={`locations-from-${warehouseId}`}
              fetcher={s => masterApi.getLocations({ search: s, page_size: 20, ...(warehouseId ? { warehouse_id: warehouseId } : {}) })}
              getKey={l => l.id}
              getLabel={l => l.code}
              onSelect={l => { setFromLocationId(l.id); setFromLocationLabel(l.code) }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Destino</label>
            <Combobox<LocationLite>
              placeholder="Ubicación destino…"
              value={toLocationId}
              displayLabel={toLocationLabel}
              queryKey={`locations-to-${warehouseId}`}
              fetcher={s => masterApi.getLocations({ search: s, page_size: 20, ...(warehouseId ? { warehouse_id: warehouseId } : {}) })}
              getKey={l => l.id}
              getLabel={l => l.code}
              onSelect={l => { setToLocationId(l.id); setToLocationLabel(l.code) }}
            />
          </div>
          <div className="flex gap-2">
            <Input type="number" label="Cantidad" value={quantity} onChange={e => setQuantity(e.target.value)} />
          </div>
        </div>
        <div className="mt-3 flex justify-end">
          <Button size="sm" disabled={!formValid} loading={transferMut.isPending}
            onClick={() => transferMut.mutate()}>
            <ArrowRightLeft className="h-4 w-4" /> Transferir
          </Button>
        </div>
      </Card>

      <Card padding={false}>
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Transferencias recientes</h2>
        </div>
        <Table>
          <Thead>
            <Tr>
              <Th>Producto</Th>
              <Th>Origen</Th>
              <Th>Destino</Th>
              <Th>Cantidad</Th>
              <Th>Hora</Th>
            </Tr>
          </Thead>
          <Tbody>
            {!recentTransfers.length ? (
              <EmptyRow cols={5} message="Aún no se han registrado transferencias" />
            ) : (
              recentTransfers.map(t => (
                <Tr key={t.id}>
                  <Td className="text-xs">{t.productLabel}</Td>
                  <Td className="text-xs text-gray-500">{t.fromLabel}</Td>
                  <Td className="text-xs text-gray-500">{t.toLabel}</Td>
                  <Td>{fmt.number(t.quantity)}</Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(t.at)}</Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
      </Card>

      <Card padding={false}>
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Reservas activas</h2>
        </div>
        <Table>
          <Thead>
            <Tr>
              <Th>Producto</Th>
              <Th>Cantidad</Th>
              <Th>Tipo</Th>
              <Th>Referencia</Th>
              <Th>Expira</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 6 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-16" /></Td>
                  ))}
                </Tr>
              ))
            ) : !reservations?.items.length ? (
              <EmptyRow cols={6} message="No hay reservas activas" />
            ) : (
              reservations.items.map(r => (
                <Tr key={r.id}>
                  <Td className="text-xs">{r.product_name ?? r.product_id}</Td>
                  <Td>{fmt.number(r.quantity)}</Td>
                  <Td className="text-xs text-gray-500 capitalize">{r.reservation_type}</Td>
                  <Td className="text-xs text-gray-500">{r.reference_type} {r.reference_number}</Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(r.expires_at)}</Td>
                  <Td>
                    <button onClick={() => cancelMut.mutate(r.id)} title="Cancelar reserva"
                      className="text-red-500 hover:text-red-700 transition-colors">
                      <XCircle className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
      </Card>
    </div>
  )
}
