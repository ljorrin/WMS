import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, ArrowDownUp } from 'lucide-react'
import { inventoryApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import { cn } from '@/utils/cn'

const MOVEMENT_TYPES = [
  { value: '', label: 'Todos los tipos' },
  { value: 'receipt', label: 'Recepción' },
  { value: 'putaway', label: 'Putaway' },
  { value: 'transfer', label: 'Transferencia' },
  { value: 'pick', label: 'Picking' },
  { value: 'adjustment', label: 'Ajuste' },
  { value: 'cycle_count', label: 'Conteo cíclico' },
]

// Movimientos de entrada (positivos) vs salida (negativos) según signo de cantidad
function MovementType({ type }: { type: string }) {
  const inbound = ['receipt', 'putaway', 'adjustment_in', 'return'].some(t => type.includes(t))
  return <Badge status={inbound ? 'active' : 'in_progress'} label={type.replace(/_/g, ' ')} />
}

const PAGE_SIZE = 25

export function MovementsPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['movements', page, search, type],
    queryFn: () => inventoryApi.getMovements({
      page,
      page_size: PAGE_SIZE,
      search: search || undefined,
      movement_type: type || undefined,
    }),
    placeholderData: prev => prev,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Movimientos de Inventario</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} movimientos (kárdex global)</p>
        </div>
      </div>

      <Card padding={false}>
        <div className="p-4 border-b border-gray-100 flex flex-col sm:flex-row gap-3">
          <div className="flex items-center gap-2 flex-1">
            <Search className="h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por producto, ubicación, referencia..."
              className="flex-1 text-sm outline-none placeholder:text-gray-400"
            />
          </div>
          <select
            value={type}
            onChange={e => { setType(e.target.value); setPage(1) }}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700"
          >
            {MOVEMENT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>

        <Table>
          <Thead>
            <Tr>
              <Th>Tipo</Th>
              <Th>Producto</Th>
              <Th>Ubicación</Th>
              <Th>Lote</Th>
              <Th>Cantidad</Th>
              <Th>Referencia</Th>
              <Th>Fecha</Th>
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
              <EmptyRow cols={7} message="No hay movimientos registrados" />
            ) : (
              data.items.map(m => (
                <Tr key={m.id}>
                  <Td><MovementType type={m.movement_type} /></Td>
                  <Td>
                    <p className="font-medium text-gray-900">{m.product_name ?? m.product_id}</p>
                  </Td>
                  <Td>
                    <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                      {m.location_code ?? m.location_id}
                    </span>
                  </Td>
                  <Td className="text-xs text-gray-500">{m.batch_number ?? '—'}</Td>
                  <Td>
                    <span className={cn(
                      'font-semibold inline-flex items-center gap-1',
                      m.quantity < 0 ? 'text-red-600' : 'text-green-700'
                    )}>
                      <ArrowDownUp className="h-3 w-3" />
                      {fmt.number(m.quantity)} {m.uom_code ?? ''}
                    </span>
                  </Td>
                  <Td className="text-xs text-gray-500">
                    {m.reference_type ? `${m.reference_type}` : '—'}
                  </Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(m.created_at)}</Td>
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
