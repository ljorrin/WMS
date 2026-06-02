import { useQuery } from '@tanstack/react-query'
import { inboundApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Badge } from '@/components/ui/Badge'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'

export function GRNDetailModal({ grnId, onClose }: { grnId: string | null; onClose: () => void }) {
  const { data: grn, isLoading } = useQuery({
    queryKey: ['grn', grnId],
    queryFn: () => inboundApi.getGRN(grnId!),
    enabled: !!grnId,
  })

  return (
    <Modal
      open={!!grnId}
      onClose={onClose}
      title={grn ? `Recepción ${grn.grn_number}` : 'Recepción'}
      size="lg"
    >
      {isLoading || !grn ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-4 w-full animate-pulse rounded bg-gray-100" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Estado"><Badge status={grn.status} /></Field>
            <Field label="Modo"><span className="capitalize">{grn.receiving_mode ?? '—'}</span></Field>
            <Field label="Requiere QC">{grn.requires_qc ? 'Sí' : 'No'}</Field>
            <Field label="Recibido">{fmt.datetime(grn.received_at)}</Field>
            {grn.product_temp_celsius != null && (
              <Field label="Temp. producto">{grn.product_temp_celsius}°C</Field>
            )}
          </div>

          <Table>
            <Thead>
              <Tr>
                <Th>Producto</Th>
                <Th>Recibido</Th>
                <Th>Rechazado</Th>
                <Th>Ubicación</Th>
                <Th>Lote</Th>
                <Th>Vence</Th>
              </Tr>
            </Thead>
            <Tbody>
              {!grn.lines?.length ? (
                <EmptyRow cols={6} message="Sin líneas" />
              ) : (
                grn.lines.map(l => (
                  <Tr key={l.id}>
                    <Td><span className="font-mono text-xs">{l.product_id}</span></Td>
                    <Td className="text-green-700">{fmt.number(l.quantity_received)}</Td>
                    <Td className={l.quantity_rejected > 0 ? 'text-red-600' : 'text-gray-400'}>
                      {fmt.number(l.quantity_rejected)}
                    </Td>
                    <Td><span className="font-mono text-xs">{l.location_id}</span></Td>
                    <Td className="text-xs">{l.batch_number ?? '—'}</Td>
                    <Td className="text-xs">{l.expiry_date ? fmt.date(l.expiry_date) : '—'}</Td>
                  </Tr>
                ))
              )}
            </Tbody>
          </Table>
        </div>
      )}
    </Modal>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <div className="mt-0.5 text-sm text-gray-800">{children}</div>
    </div>
  )
}
