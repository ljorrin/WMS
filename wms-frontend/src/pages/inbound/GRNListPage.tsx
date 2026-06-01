import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, ClipboardCheck, Thermometer } from 'lucide-react'
import { inboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20

export function GRNListPage() {
  const [page, setPage] = useState(1)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['grns', page],
    queryFn: () => inboundApi.getGRNs({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const confirmMut = useMutation({
    mutationFn: (id: string) => inboundApi.confirmGRN(id),
    onSuccess: () => {
      toast.success('GRN confirmado — stock disponible en staging')
      qc.invalidateQueries({ queryKey: ['grns'] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Recepciones (GRN)</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} recepciones</p>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>Modo</Th>
              <Th>QC</Th>
              <Th>Cadena de frío</Th>
              <Th># Líneas</Th>
              <Th>Recibido</Th>
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
              <EmptyRow cols={8} message="No hay recepciones registradas" />
            ) : (
              data.items.map(grn => (
                <Tr key={grn.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{grn.grn_number}</span></Td>
                  <Td><Badge status={grn.status} /></Td>
                  <Td className="text-xs text-gray-500 capitalize">{grn.receiving_mode ?? '—'}</Td>
                  <Td>
                    {grn.requires_qc
                      ? <Badge status="pending" label="Requiere" />
                      : <span className="text-xs text-gray-400">No</span>}
                  </Td>
                  <Td>
                    {grn.product_temp_celsius != null ? (
                      <span className="inline-flex items-center gap-1 text-xs text-cyan-700">
                        <Thermometer className="h-3 w-3" /> {grn.product_temp_celsius}°C
                      </span>
                    ) : <span className="text-xs text-gray-400">—</span>}
                  </Td>
                  <Td className="text-center">{grn.lines?.length ?? 0}</Td>
                  <Td className="text-xs text-gray-400">{fmt.datetime(grn.received_at)}</Td>
                  <Td>
                    <div className="flex gap-1">
                      {grn.status === 'in_progress' && (
                        <button onClick={() => confirmMut.mutate(grn.id)} title="Confirmar recepción"
                          className="text-green-600 hover:text-green-800 transition-colors">
                          <CheckCircle className="h-4 w-4" />
                        </button>
                      )}
                      {grn.requires_qc && grn.status === 'confirmed' && (
                        <span title="Pendiente de control de calidad" className="text-amber-500">
                          <ClipboardCheck className="h-4 w-4" />
                        </span>
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
    </div>
  )
}
