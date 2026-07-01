import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Filter, Download, X } from 'lucide-react'
import { inventoryApi, warehouseApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'
import { cn } from '@/utils/cn'
import toast from 'react-hot-toast'

const STOCK_STATUSES = ['', 'active', 'quarantine', 'damaged', 'expired']
const PAGE_SIZE = 20

export function StockPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showFilters, setShowFilters] = useState(false)

  // Filtros avanzados
  const [warehouseId, setWarehouseId] = useState('')
  const [stockStatus, setStockStatus] = useState('')
  const [onlyNearExpiry, setOnlyNearExpiry] = useState(false)
  const [onlyZeroAvailable, setOnlyZeroAvailable] = useState(false)

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const activeFiltersCount = [warehouseId, stockStatus, onlyNearExpiry, onlyZeroAvailable]
    .filter(Boolean).length

  const queryParams = {
    page,
    page_size: PAGE_SIZE,
    search: search || undefined,
    warehouse_id: warehouseId || undefined,
    status: stockStatus || undefined,
    near_expiry: onlyNearExpiry || undefined,
    zero_available: onlyZeroAvailable || undefined,
  }

  const { data, isLoading } = useQuery({
    queryKey: ['stock', page, search, warehouseId, stockStatus, onlyNearExpiry, onlyZeroAvailable],
    queryFn: () => inventoryApi.getStock(queryParams),
    placeholderData: prev => prev,
  })

  const clearFilters = () => {
    setWarehouseId(''); setStockStatus(''); setOnlyNearExpiry(false); setOnlyZeroAvailable(false)
  }

  const exportCSV = () => {
    if (!data?.items.length) {
      toast.error('No hay datos para exportar')
      return
    }
    const headers = ['Producto', 'SKU', 'Ubicación', 'Lote', 'Vencimiento', 'Disponible', 'Reservado', 'Total', 'Estado', 'Actualizado']
    const rows = data.items.map(row => [
      row.product_name ?? row.product_id,
      row.product_sku ?? '',
      row.location_code ?? row.location_id,
      row.batch_number ?? '',
      row.expiry_date ? fmt.date(row.expiry_date) : '',
      row.quantity_available,
      row.quantity_reserved,
      row.quantity_on_hand,
      row.status,
      fmt.datetime(row.updated_at),
    ])

    const csvContent = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n')

    const blob = new Blob(['﻿' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `stock-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success(`${data.items.length} registros exportados`)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Stock por Ubicación</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} registros</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowFilters(f => !f)}
            className={cn(activeFiltersCount > 0 && 'border-primary-400 text-primary-700')}
          >
            <Filter className="h-4 w-4" />
            Filtros
            {activeFiltersCount > 0 && (
              <span className="ml-1 rounded-full bg-primary-600 text-white text-[10px] font-bold px-1.5 py-0.5 leading-none">
                {activeFiltersCount}
              </span>
            )}
          </Button>
          <Button variant="secondary" size="sm" onClick={exportCSV}>
            <Download className="h-4 w-4" /> Exportar CSV
          </Button>
        </div>
      </div>

      {/* Panel de filtros avanzados */}
      {showFilters && (
        <Card>
          <div className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="flex flex-col gap-1 min-w-[180px]">
              <label className="text-sm font-medium text-gray-700">Bodega</label>
              <select
                value={warehouseId}
                onChange={e => { setWarehouseId(e.target.value); setPage(1) }}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
              >
                <option value="">Todas las bodegas</option>
                {warehouses?.items.map(w => (
                  <option key={w.id} value={w.id}>{w.code} — {w.name}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1 min-w-[160px]">
              <label className="text-sm font-medium text-gray-700">Estado de stock</label>
              <select
                value={stockStatus}
                onChange={e => { setStockStatus(e.target.value); setPage(1) }}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
              >
                {STOCK_STATUSES.map(s => (
                  <option key={s} value={s}>{s ? s.replace(/_/g, ' ') : 'Todos los estados'}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-4 items-center pb-1">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={onlyNearExpiry}
                  onChange={e => { setOnlyNearExpiry(e.target.checked); setPage(1) }}
                />
                Solo próximos a vencer
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={onlyZeroAvailable}
                  onChange={e => { setOnlyZeroAvailable(e.target.checked); setPage(1) }}
                />
                Sin disponible
              </label>
            </div>
            {activeFiltersCount > 0 && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4" /> Limpiar filtros
              </Button>
            )}
          </div>
        </Card>
      )}

      {/* Búsqueda + Tabla */}
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
            {search && (
              <button onClick={() => { setSearch(''); setPage(1) }}
                className="text-gray-400 hover:text-gray-600">
                <X className="h-4 w-4" />
              </button>
            )}
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
              <EmptyRow cols={8} message="No hay stock registrado con los filtros aplicados" />
            ) : (
              data?.items.map(row => {
                const isExpired = row.expiry_date && new Date(row.expiry_date) < new Date()
                return (
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
                          <p className={cn('text-xs', isExpired ? 'text-red-500 font-semibold' : 'text-gray-400')}>
                            {fmt.date(row.expiry_date)}
                          </p>
                        )}
                      </div>
                    </Td>
                    <Td>
                      <span className={cn('font-semibold',
                        row.quantity_available === 0 ? 'text-gray-400' : 'text-green-700')}>
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
                )
              })
            )}
          </Tbody>
        </Table>

        {data && data.total > PAGE_SIZE && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <p className="text-xs text-gray-500">
              Mostrando {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, data.total)} de {data.total}
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page === 1}
                onClick={() => setPage(p => p - 1)}>Anterior</Button>
              <Button variant="secondary" size="sm"
                disabled={page * PAGE_SIZE >= data.total}
                onClick={() => setPage(p => p + 1)}>Siguiente</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
