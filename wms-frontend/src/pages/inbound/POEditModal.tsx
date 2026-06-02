import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { inboundApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import type { PurchaseOrder, PurchaseOrderUpdate } from '@/types'
import toast from 'react-hot-toast'

/**
 * Edición de cabecera de una Orden de Compra.
 * El backend solo permite editar OCs en estado DRAFT (las líneas no se editan aquí).
 */
export function POEditModal({ po, onClose }: { po: PurchaseOrder | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<PurchaseOrderUpdate>({})

  useEffect(() => {
    if (po) {
      setForm({
        supplier_po_reference: po.supplier_po_reference ?? '',
        expected_delivery_date: po.expected_delivery_date ?? '',
        payment_terms: po.payment_terms ?? '',
        incoterms: po.incoterms ?? '',
        erp_reference: po.erp_reference ?? '',
        notes: po.notes ?? '',
      })
    }
  }, [po])

  const set = (patch: Partial<PurchaseOrderUpdate>) => setForm(f => ({ ...f, ...patch }))

  const mut = useMutation({
    mutationFn: () => {
      // Solo enviar campos con valor (el backend ignora los nulos)
      const payload: PurchaseOrderUpdate = {}
      for (const [k, v] of Object.entries(form)) {
        if (v !== '' && v !== undefined) (payload as Record<string, unknown>)[k] = v
      }
      return inboundApi.updatePO(po!.id, payload)
    },
    onSuccess: () => {
      toast.success('Orden de compra actualizada')
      qc.invalidateQueries({ queryKey: ['pos'] })
      qc.invalidateQueries({ queryKey: ['po', po!.id] })
      onClose()
    },
    onError: () => toast.error('No se pudo actualizar la orden de compra'),
  })

  return (
    <Modal
      open={!!po}
      onClose={onClose}
      title={po ? `Editar ${po.po_number}` : 'Editar orden'}
      description="Solo se pueden editar órdenes en estado borrador (DRAFT)."
      size="md"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancelar</Button>
          <Button size="sm" loading={mut.isPending} onClick={() => mut.mutate()}>Guardar cambios</Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Input label="Referencia OC proveedor" value={form.supplier_po_reference ?? ''}
          onChange={e => set({ supplier_po_reference: e.target.value })} />
        <Input label="Entrega esperada" type="date" value={form.expected_delivery_date ?? ''}
          onChange={e => set({ expected_delivery_date: e.target.value })} />
        <Input label="Condiciones de pago" value={form.payment_terms ?? ''}
          onChange={e => set({ payment_terms: e.target.value })} />
        <Input label="Incoterms" value={form.incoterms ?? ''}
          onChange={e => set({ incoterms: e.target.value })} />
        <Input label="Referencia ERP" value={form.erp_reference ?? ''}
          onChange={e => set({ erp_reference: e.target.value })} />
        <Input label="Notas" value={form.notes ?? ''}
          onChange={e => set({ notes: e.target.value })} />
      </div>
    </Modal>
  )
}
