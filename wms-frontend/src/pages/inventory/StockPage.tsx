import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Filter, Download } from 'lucide-react'
import { inventoryApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'

export function StockPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['stock', page, search],
    queryFn: () => inventoryApi.getStock({ page, page_size: 20, search: search || undefined }),
    placeholderData: prev => prev,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Stock por Ubicación</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} registros</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm">
            <Filter className="h-4 w-4" /> Filtros
          </Button>
          <Button variant="secondary" size="sm">
            <Download className="h-4 w-4" /> Exportar
          </Button>
        </div>
      </div>

      {/* Search */}
      <Card padding={false}>
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por SKU, nombre, ubicación..."
              className="flex-1 text-sm outline-none placeholder:text-gray-400"
            />
          </div>
        </div>

        <Table>
          <Thead>
            <Tr>
              <Th>Producto</Th>
              <Th>Ubicación</Th>
              <Th>Lote / Vence</Th>
              <Th>Disponible</Th>
              <Th>Reservado</Th>
              <Th>Total</Th>
              <Th>Estado</Th>
              <Th>Actualizado</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>
                  {Array.from({ length: 8 }).map((_, j) => (
                    <Td key={j}>
                      <div className="h-4 rounded bg-gray-100 animate-pulse w-20" />
                    </Td>
                  ))}
                </Tr>
              ))
            ) : data?.items.length === 0 ? (
              <EmptyRow cols={8} message="No hay stock registrado" />
            ) : (
              data?.items.map(row => (
                <Tr key={row.id}>
                  <Td>
                    <div>
                      <p className="font-medium text-gray-900">{row.product_name ?? row.product_id}</p>
                      <p className="text-xs text-gray-400 font-mono">{row.product_sku}</p>
                    </div>
                  </Td>
                  <Td>
                    <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                      {row.location_code ?? row.location_id}
                    </span>
                  </Td>
                  <Td>
                    <div>
                      <p className="text-xs">{row.batch_number ?? '—'}</p>
                      {row.expiry_date && (
                        <p className={`text-xs ${new Date(row.expiry_date) < new Date() ? 'text-red-500' : 'text-gray-400'}`}>
                          {fmt.date(row.expiry_date)}
                        </p>
                      )}
                    </div>
                  </Td>
                  <Td>
                    <span className="font-semibold text-green-700">
                      {fmt.number(row.quantity_available)}
                    </span>
                  </Td>
                  <Td>
                    <span className="text-amber-600">{fmt.number(row.quantity_reserved)}</span>
                  </Td>
                  <Td className="font-medium">{fmt.number(row.quantity_on_hand)}</Td>
                  <Td><Badge status={row.status} /></Td>
                  <Td className="text-xs text-gray-400">{fmt.relative(row.updated_at)}</Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>

        {/* Pagination */}
        {data && data.total > 20 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <p className="text-xs text-gray-500">
              Mostrando {(page - 1) * 20 + 1}–{Math.min(page * 20, data.total)} de {data.total}
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page === 1}
                onClick={() => setPage(p => p - 1)}>Anterior</Button>
              <Button variant="secondary" size="sm"
                disabled={page * 20 >= data.total}
                onClick={() => setPage(p => p + 1)}>Siguiente</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
