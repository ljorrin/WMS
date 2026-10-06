import { useState } from 'react'
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { outboundApi, masterApi, warehouseApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Combobox } from '@/components/ui/Combobox'
import type { Product, Customer, CargoType } from '@/types'
import toast from 'react-hot-toast'

interface SOLineDraft {
  key: string
  product_id: string
  product_label: string
  quantity_ordered: string
  unit_price: string
}

const emptyLine = (): SOLineDraft => ({
  key: crypto.randomUUID(),
  product_id: '',
  product_label: '',
  quantity_ordered: '',
  unit_price: '',
})

interface ShipTo {
  name: string; address: string; city: string; phone: string; contact: string
  lat: string; lon: string; windowFrom: string; windowTo: string; serviceMin: string
}

const EMPTY_SHIP_TO: ShipTo = {
  name: '', address: '', city: '', phone: '', contact: '',
  lat: '', lon: '', windowFrom: '', windowTo: '', serviceMin: '',
}

const shipToFromCustomer = (c: Customer): ShipTo => ({
  name: c.name ?? '', address: c.delivery_address ?? '', city: c.delivery_city ?? '',
  phone: c.contact_phone ?? '', contact: c.contact_name ?? '',
  lat: c.delivery_latitude != null ? String(Number(c.delivery_latitude)) : '',
  lon: c.delivery_longitude != null ? String(Number(c.delivery_longitude)) : '',
  windowFrom: '', windowTo: '',
  serviceMin: c.service_time_min != null ? String(c.service_time_min) : '',
})

// datetime-local (hora del navegador) → ISO-8601 con zona
const toIso = (v: string) => (v ? new Date(v).toISOString() : undefined)

const SERVICE_LEVELS = [
  { value: 'standard', label: 'Estándar' },
  { value: 'express', label: 'Express' },
  { value: 'same_day', label: 'Mismo día' },
  { value: 'scheduled', label: 'Programada' },
]
const CARGO_TYPES: { value: CargoType | ''; label: string }[] = [
  { value: '', label: 'Automático (según productos)' },
  { value: 'consumo_masivo', label: 'Consumo masivo' },
  { value: 'refrigerada', label: 'Refrigerada' },
  { value: 'farmaceutica', label: 'Farmacéutica' },
  { value: 'peligrosa', label: 'Peligrosa' },
  { value: 'fragil', label: 'Frágil' },
  { value: 'repuestos', label: 'Repuestos' },
]

const CURRENCIES = ['USD', 'PAB']
const INCOTERMS = ['EXW', 'FCA', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP', 'FAS', 'FOB', 'CFR', 'CIF']

interface Props {
  open: boolean
  onClose: () => void
}

export function SOFormModal({ open, onClose }: Props) {
  const qc = useQueryClient()

  const [customerId, setCustomerId] = useState('')
  const [customerLabel, setCustomerLabel] = useState('')
  const [warehouseId, setWarehouseId] = useState('')
  const [warehouseLabel, setWarehouseLabel] = useState('')
  const [priority, setPriority] = useState('5')
  const [currency, setCurrency] = useState('USD')
  const [deliveryDate, setDeliveryDate] = useState('')
  const [incoterms, setIncoterms] = useState('')
  const [notes, setNotes] = useState('')
  const [lines, setLines] = useState<SOLineDraft[]>([emptyLine()])
  const [shipTo, setShipTo] = useState<ShipTo>(EMPTY_SHIP_TO)
  const [serviceLevel, setServiceLevel] = useState('standard')
  const [cargoType, setCargoType] = useState<CargoType | ''>('')
  const patchShipTo = (p: Partial<ShipTo>) => setShipTo(s => ({ ...s, ...p }))

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
    enabled: open,
  })

  const reset = () => {
    setCustomerId(''); setCustomerLabel(''); setWarehouseId(''); setWarehouseLabel('')
    setPriority('5'); setCurrency('USD'); setDeliveryDate('')
    setIncoterms(''); setNotes(''); setLines([emptyLine()])
    setShipTo(EMPTY_SHIP_TO); setServiceLevel('standard'); setCargoType('')
  }

  const updateLine = (key: string, patch: Partial<SOLineDraft>) =>
    setLines(ls => ls.map(l => l.key === key ? { ...l, ...patch } : l))

  const validLines = lines.filter(
    l => l.product_id && Number(l.quantity_ordered) > 0 && Number(l.unit_price) >= 0
  )

  const latNum = Number(shipTo.lat), lonNum = Number(shipTo.lon)
  const geoInvalid = (shipTo.lat !== '' || shipTo.lon !== '') && (
    shipTo.lat === '' || shipTo.lon === '' || !Number.isFinite(latNum) || !Number.isFinite(lonNum) ||
    Math.abs(latNum) > 90 || Math.abs(lonNum) > 180)
  const windowInvalid = !!shipTo.windowFrom && !!shipTo.windowTo && shipTo.windowTo <= shipTo.windowFrom

  const canSubmit = !!customerId && warehouseId &&
    validLines.length > 0 && !geoInvalid && !windowInvalid

  const createMut = useMutation({
    mutationFn: () => outboundApi.createSO({
      customer_id: customerId,
      warehouse_id: warehouseId,
      priority: Number(priority),
      currency,
      requested_delivery_date: deliveryDate || undefined,
      incoterms: incoterms || undefined,
      delivery_instructions: notes || undefined,
      service_level: serviceLevel,
      cargo_type: cargoType || undefined,
      // Datos de entrega para el TMS (lo vacío lo completa el backend desde la ficha del cliente)
      ship_to_name: shipTo.name || undefined,
      ship_to_address: shipTo.address || undefined,
      ship_to_city: shipTo.city || undefined,
      ship_to_phone: shipTo.phone || undefined,
      ship_to_contact_name: shipTo.contact || undefined,
      ship_to_latitude: shipTo.lat !== '' ? latNum : undefined,
      ship_to_longitude: shipTo.lon !== '' ? lonNum : undefined,
      delivery_window_start: toIso(shipTo.windowFrom),
      delivery_window_end: toIso(shipTo.windowTo),
      service_time_min: shipTo.serviceMin !== '' ? Number(shipTo.serviceMin) : undefined,
      lines: validLines.map(l => ({
        product_id: l.product_id,
        quantity_ordered: Number(l.quantity_ordered),
        unit_price: Number(l.unit_price),
      })),
    }),
    onSuccess: () => {
      toast.success('Orden de venta creada')
      qc.invalidateQueries({ queryKey: ['sos'] })
      reset(); onClose()
    },
    onError: () => toast.error('No se pudo crear la orden de venta'),
  })

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose() }}
      title="Nueva Orden de Venta"
      description="Crea una SO en borrador. Después de crearla, confírmala para reservar stock."
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={() => { reset(); onClose() }}>Cancelar</Button>
          <Button size="sm" disabled={!canSubmit} loading={createMut.isPending}
            onClick={() => createMut.mutate()}>
            Crear SO
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Cliente</label>
            <Combobox<Customer>
              placeholder="Buscar cliente…"
              value={customerId}
              displayLabel={customerLabel}
              queryKey="customers-so"
              fetcher={s => masterApi.getCustomers({ search: s, page_size: 20, is_active: true })}
              getKey={c => c.id}
              getLabel={c => `${c.code} — ${c.name}`}
              onSelect={c => {
                setCustomerId(c.id); setCustomerLabel(`${c.code} — ${c.name}`)
                setShipTo(shipToFromCustomer(c))
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Bodega</label>
            <select
              value={warehouseId}
              onChange={e => {
                setWarehouseId(e.target.value)
                const w = warehouses?.items.find(x => x.id === e.target.value)
                setWarehouseLabel(w ? `${w.code} — ${w.name}` : '')
              }}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
            >
              <option value="">Seleccionar…</option>
              {warehouses?.items.map(w => (
                <option key={w.id} value={w.id}>{w.code} — {w.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Prioridad</label>
            <select value={priority} onChange={e => setPriority(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              {Array.from({ length: 10 }, (_, i) => i + 1).map(p => (
                <option key={p} value={p}>{p}{p === 1 ? ' (urgente)' : p === 10 ? ' (mínima)' : ''}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Moneda</label>
            <select value={currency} onChange={e => setCurrency(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Incoterms</label>
            <select value={incoterms} onChange={e => setIncoterms(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              <option value="">Sin incoterms</option>
              {INCOTERMS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Fecha de entrega solicitada</label>
          <input
            type="date"
            value={deliveryDate}
            onChange={e => setDeliveryDate(e.target.value)}
            className="h-9 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm"
          />
        </div>

        {/* Entrega (TMS) */}
        <div className="rounded-lg border border-gray-100 p-3 space-y-3">
          <div>
            <p className="text-sm font-semibold text-gray-800">Entrega (TMS)</p>
            <p className="text-xs text-gray-500">
              Se completa con la ficha del cliente; ajústalo si la entrega es en otra dirección.
              Las coordenadas permiten al TMS rutear sin geocodificar.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <Input label="Dirección" value={shipTo.address}
                onChange={e => patchShipTo({ address: e.target.value, lat: '', lon: '' })}
                placeholder="Calle, edificio, local" />
            </div>
            <Input label="Ciudad" value={shipTo.city} onChange={e => patchShipTo({ city: e.target.value })} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <Input label="Latitud" value={shipTo.lat} onChange={e => patchShipTo({ lat: e.target.value })}
              placeholder="9.0110" />
            <Input label="Longitud" value={shipTo.lon} onChange={e => patchShipTo({ lon: e.target.value })}
              placeholder="-79.4700"
              error={geoInvalid ? 'Coordenadas inválidas' : undefined} />
            <Input label="Recibe" value={shipTo.contact} onChange={e => patchShipTo({ contact: e.target.value })} />
            <Input label="Teléfono" value={shipTo.phone} onChange={e => patchShipTo({ phone: e.target.value })} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Input label="Ventana desde" type="datetime-local" value={shipTo.windowFrom}
              onChange={e => patchShipTo({ windowFrom: e.target.value })} />
            <Input label="Ventana hasta" type="datetime-local" value={shipTo.windowTo}
              onChange={e => patchShipTo({ windowTo: e.target.value })}
              error={windowInvalid ? 'Debe ser posterior al inicio' : undefined} />
            <Input label="Descarga (min)" type="number" min="0" max="600" value={shipTo.serviceMin}
              onChange={e => patchShipTo({ serviceMin: e.target.value })} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Nivel de servicio</label>
              <select value={serviceLevel} onChange={e => setServiceLevel(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {SERVICE_LEVELS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Tipo de mercancía</label>
              <select value={cargoType} onChange={e => setCargoType(e.target.value as CargoType | '')}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {CARGO_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
          </div>
        </div>

        {/* Líneas */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-semibold text-gray-800">Líneas de producto</label>
            <Button variant="ghost" size="sm" onClick={() => setLines(ls => [...ls, emptyLine()])}>
              <Plus className="h-4 w-4" /> Agregar línea
            </Button>
          </div>
          <div className="space-y-2">
            {lines.map((line, idx) => (
              <div key={line.key} className="rounded-lg border border-gray-100 bg-gray-50/50 p-3">
                <div className="grid grid-cols-12 items-end gap-2">
                  <div className="col-span-5">
                    <Combobox<Product>
                      placeholder="Buscar producto…"
                      value={line.product_id}
                      displayLabel={line.product_label}
                      queryKey={`products-so-line-${idx}`}
                      fetcher={s => masterApi.getProducts({ search: s, page_size: 20, status: 'active' })}
                      getKey={p => p.id}
                      getLabel={p => `${p.sku} — ${p.name}`}
                      onSelect={p => updateLine(line.key, { product_id: p.id, product_label: `${p.sku} — ${p.name}` })}
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="Cantidad"
                      value={line.quantity_ordered}
                      onChange={e => updateLine(line.key, { quantity_ordered: e.target.value })}
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="Precio unit."
                      value={line.unit_price}
                      onChange={e => updateLine(line.key, { unit_price: e.target.value })}
                    />
                  </div>
                  <div className="col-span-1 flex justify-center pb-1">
                    {lines.length > 1 && (
                      <button
                        onClick={() => setLines(ls => ls.filter(l => l.key !== line.key))}
                        className="text-red-500 hover:text-red-700"
                        title="Eliminar línea"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <Input
          label="Notas (opcional)"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Instrucciones especiales de entrega"
        />
      </div>
    </Modal>
  )
}
