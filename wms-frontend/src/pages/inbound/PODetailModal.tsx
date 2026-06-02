import { useQuery } from '@tanstack/react-query'
import { inboundApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Badge } from '@/components/ui/Badge'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { fmt } from '@/utils/format'

export function PODetailModal({ poId, onClose }: { poId: string | null; onClose: () => void }) {
  const { data: po, isLoading } = useQuery({
    queryKey: ['po', poId],
    queryFn: () => inboundApi.getPO(poId!),
    enabled: !!poId,
  })

  return (
    <Modal
      open={!!poId}
      onClose={onClose}
      title={po ? `Orden ${po.po_number}` : 'Orden de compra'}
      description={po ? undefined : 'Cargando…'}
      size="lg"
    >
      {isLoading || !po ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-4 w-full animate-pulse rounded bg-gray-100" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Estado"><Badge status={po.status} /></Field>
            <Field label="Proveedor"><span className="font-mono text-xs">{po.supplier_id}</span></Field>
            <Field label="Fecha orden">{fmt.date(po.order_date)}</Field>
            <Field label="Entrega esperada">{po.expected_delivery_date ? fmt.date(po.expected_delivery_date) : '—'}</Field>
          </div>

          <Table>
            <Thead>
              <Tr>
                <Th>Producto</Th>
                <Th>Ordenado</Th>
                <Th>Recibido</Th>
                <Th>Pendiente</Th>
                <Th>Costo U.</Th>
                <Th>Estado</Th>
              </Tr>
            </Thead>
            <Tbody>
              {!po.lines?.length ? (
                <EmptyRow cols={6} message="Sin líneas" />
              ) : (
                po.lines.map(l => (
                  <Tr key={l.id}>
                    <Td><span className="font-mono text-xs">{l.product_id}</span></Td>
                    <Td>{fmt.number(l.quantity_ordered)}</Td>
                    <Td className="text-green-700">{fmt.number(l.quantity_received)}</Td>
                    <Td className={l.quantity_pending > 0 ? 'text-amber-600 font-medium' : 'text-gray-400'}>
                      {fmt.number(l.quantity_pending)}
                    </Td>
                    <Td>{fmt.currency(l.unit_cost, po.currency)}</Td>
                    <Td className="text-xs capitalize text-gray-500">{l.status?.replace(/_/g, ' ')}</Td>
                  </Tr>
                ))
              )}
            </Tbody>
          </Table>

          <div className="flex justify-end text-sm text-gray-600">
            Total:&nbsp;<span className="font-semibold text-gray-900">{fmt.currency(po.total_amount, po.currency)}</span>
          </div>

          {po.status_history && po.status_history.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Historial de estados
              </h4>
              <ol className="space-y-2 border-l border-gray-200 pl-4">
                {po.status_history.map(h => (
                  <li key={h.id} className="relative">
                    <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-primary-500" />
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      {h.from_status && (
                        <span className="text-xs capitalize text-gray-400">{h.from_status.replace(/_/g, ' ')} →</span>
                      )}
                      <Badge status={h.to_status} />
                      <span className="text-xs text-gray-400">{fmt.date(h.created_at)}</span>
                    </div>
                    {h.reason && <p className="mt-0.5 text-xs text-gray-500">{h.reason}</p>}
                  </li>
                ))}
              </ol>
            </div>
          )}
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
