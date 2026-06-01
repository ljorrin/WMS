import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, ShieldX } from 'lucide-react'
import { inboundApi } from '@/api/endpoints'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import { cn } from '@/utils/cn'
import type { QualityInspection } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20
const DISPOSITIONS = [
  { value: 'accept', label: 'Aceptar', approved: true },
  { value: 'conditional_accept', label: 'Aceptar condicional', approved: true },
  { value: 'rework', label: 'Reproceso', approved: false },
  { value: 'reject', label: 'Rechazar', approved: false },
]

export function QualityPage() {
  const [page, setPage] = useState(1)
  const [target, setTarget] = useState<QualityInspection | null>(null)
  const [disposition, setDisposition] = useState('accept')
  const [notes, setNotes] = useState('')
  const [returnToVendor, setReturnToVendor] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['qc', page],
    queryFn: () => inboundApi.getQCInspections({ page, page_size: PAGE_SIZE }),
    placeholderData: prev => prev,
  })

  const resolveMut = useMutation({
    mutationFn: () => {
      const def = DISPOSITIONS.find(d => d.value === disposition)!
      return inboundApi.resolveQC(target!.id, {
        approved: def.approved,
        disposition,
        disposition_notes: notes || undefined,
        return_to_vendor: returnToVendor,
      })
    },
    onSuccess: () => {
      toast.success('Inspección resuelta')
      setTarget(null); setNotes(''); setDisposition('accept'); setReturnToVendor(false)
      qc.invalidateQueries({ queryKey: ['qc'] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Control de Calidad</h1>
          <p className="text-sm text-gray-500">{data?.total ?? 0} inspecciones</p>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Número</Th>
              <Th>Estado</Th>
              <Th>AQL</Th>
              <Th>Inspeccionado</Th>
              <Th>Aprobado</Th>
              <Th>Rechazado</Th>
              <Th>Tasa defecto</Th>
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
              <EmptyRow cols={8} message="No hay inspecciones de calidad" />
            ) : (
              data.items.map(qi => {
                const pending = ['pending', 'in_progress'].includes(qi.status)
                return (
                  <Tr key={qi.id}>
                    <Td><span className="font-mono font-medium text-primary-700">{qi.qi_number}</span></Td>
                    <Td><Badge status={qi.status} /></Td>
                    <Td className="text-xs text-gray-500">{qi.aql_level ?? '—'}</Td>
                    <Td>{fmt.number(qi.total_inspected)}</Td>
                    <Td className="text-green-700 font-medium">{fmt.number(qi.total_approved)}</Td>
                    <Td className="text-red-600">{fmt.number(qi.total_rejected)}</Td>
                    <Td>
                      <span className={cn('font-medium',
                        (qi.defect_rate ?? 0) > 5 ? 'text-red-600' : 'text-gray-700')}>
                        {qi.defect_rate != null ? `${(qi.defect_rate * 100).toFixed(1)}%` : '—'}
                      </span>
                    </Td>
                    <Td>
                      {pending && (
                        <Button size="sm" variant="secondary" onClick={() => setTarget(qi)}>
                          Resolver
                        </Button>
                      )}
                    </Td>
                  </Tr>
                )
              })
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={!!target}
        onClose={() => setTarget(null)}
        title={`Resolver inspección ${target?.qi_number ?? ''}`}
        description="Define la disposición final del material inspeccionado."
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setTarget(null)}>Cancelar</Button>
            <Button size="sm" loading={resolveMut.isPending} onClick={() => resolveMut.mutate()}>
              Confirmar disposición
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2">
            {DISPOSITIONS.map(d => (
              <button key={d.value} onClick={() => setDisposition(d.value)}
                className={cn(
                  'flex items-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors',
                  disposition === d.value
                    ? d.approved ? 'border-green-400 bg-green-50 text-green-800' : 'border-red-400 bg-red-50 text-red-800'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                )}>
                {d.approved ? <ShieldCheck className="h-4 w-4" /> : <ShieldX className="h-4 w-4" />}
                {d.label}
              </button>
            ))}
          </div>

          <Input label="Notas de disposición" value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="Justificación / observaciones" />

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" className="rounded" checked={returnToVendor}
              onChange={e => setReturnToVendor(e.target.checked)} />
            Generar devolución al proveedor (RTV) por el material rechazado
          </label>
        </div>
      </Modal>
    </div>
  )
}
