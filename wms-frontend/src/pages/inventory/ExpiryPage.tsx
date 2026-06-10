import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CalendarClock } from 'lucide-react'
import { inventoryApi, warehouseApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import { cn } from '@/utils/cn'

const DAYS_OPTIONS = [7, 15, 30, 60, 90]

export function ExpiryPage() {
  const [warehouseId, setWarehouseId] = useState('')
  const [days, setDays] = useState(30)
  const [mode, setMode] = useState<'near' | 'expired'>('near')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  // Selecciona la primera bodega disponible por defecto
  useEffect(() => {
    if (!warehouseId && warehouses?.items.length) {
      setWarehouseId(warehouses.items[0].id)
    }
  }, [warehouses, warehouseId])

  const { data, isLoading } = useQuery({
    queryKey: ['expiry', warehouseId, days, mode, page],
    queryFn: () => mode === 'near'
      ? inventoryApi.getNearExpiry(warehouseId, days, page, PAGE_SIZE)
      : inventoryApi.getExpired(warehouseId, page, PAGE_SIZE),
    enabled: !!warehouseId,
    placeholderData: prev => prev,
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Control de Vencimientos (FEFO)</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} lotes</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
            {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
          </select>
          <div className="inline-flex rounded-lg border border-gray-300 overflow-hidden">
            <button onClick={() => { setMode('near'); setPage(1); }}
              className={cn('px-3 py-1.5 text-sm', mode === 'near' ? 'bg-primary-600 text-white' : 'bg-white text-gray-600')}>
              Por vencer
            </button>
            <button onClick={() => { setMode('expired'); setPage(1); }}
              className={cn('px-3 py-1.5 text-sm', mode === 'expired' ? 'bg-red-600 text-white' : 'bg-white text-gray-600')}>
              Vencidos
            </button>
          </div>
          {mode === 'near' && (
            <select value={days} onChange={e => setDays(Number(e.target.value))}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
              {DAYS_OPTIONS.map(d => <option key={d} value={d}>Próximos {d} días</option>)}
            </select>
          )}
        </div>
      </div>

      {mode === 'expired' && data?.warning && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 shrink-0" /> {data.warning}
        </div>
      )}

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Lote</Th>
              <Th>Producto</Th>
              <Th>Vencimiento</Th>
              <Th>Días restantes</Th>
              <Th>Disponible</Th>
              <Th>En retención</Th>
              <Th>Estado</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                  ))}
                </Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={7} message={mode === 'near' ? 'No hay lotes próximos a vencer' : 'No hay lotes vencidos con stock'} />
            ) : (
              data.items.map(b => {
                const critical = (b.days_to_expiry ?? 999) <= 7 || b.is_expired
                return (
                  <Tr key={b.id} className={critical ? 'bg-red-50/40' : ''}>
                    <Td><span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{b.lot_number || (b as any).batch_number}</span></Td>
                    <Td className="text-gray-900 font-medium text-sm">{(b as any).product_name ?? b.product_id}</Td>
                    <Td className={cn('text-xs', critical && 'text-red-600 font-semibold')}>
                      <span className="inline-flex items-center gap-1">
                        <CalendarClock className="h-3 w-3" /> {fmt.date(b.expiry_date)}
                      </span>
                    </Td>
                    <Td>
                      {b.is_expired ? (
                        <Badge status="expired" label="Vencido" />
                      ) : (
                        <span className={cn('font-semibold',
                          (b.days_to_expiry ?? 0) <= 7 ? 'text-red-600'
                            : (b.days_to_expiry ?? 0) <= 30 ? 'text-amber-600' : 'text-gray-600')}>
                          {b.days_to_expiry ?? '—'} días
                        </span>
                      )}
                    </Td>
                    <Td className="font-medium text-green-700">{fmt.number(b.quantity_available)}</Td>
                    <Td className="text-amber-600">{fmt.number(b.quantity_on_hold)}</Td>
                    <Td><Badge status={b.status} /></Td>
                  </Tr>
                )
              })
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>
    </div>
  )
}
