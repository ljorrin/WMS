import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { Plus, Pencil, Package, Users, UserCheck, MapPin, Box, X } from 'lucide-react'
import { masterApi, warehouseApi } from '@/api/endpoints'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { Product, Supplier, Customer, BoxType, LocationLite } from '@/types'
import toast from 'react-hot-toast'

// ─── Tipos locales ────────────────────────────────────────
type Tab = 'productos' | 'proveedores' | 'clientes' | 'tipos-caja' | 'ubicaciones'

const PAGE_SIZE = 25

// ─── Constantes ───────────────────────────────────────────
const TRACEABILITY_TYPES = ['none', 'lot', 'serial', 'lot_expiry']
const STORAGE_CONDITIONS = ['ambient', 'controlled', 'refrigerated', 'frozen', 'ultra_frozen']
const ROTATION_STRATEGIES = ['FEFO', 'FIFO', 'LIFO', 'LEFO']
const LOCATION_TYPES = ['standard', 'bulk', 'floor', 'mezzanine', 'cold_room', 'hazmat', 'quarantine', 'receiving', 'shipping', 'staging', 'cross_dock', 'damaged', 'returns']
const SUPPLIER_TYPES = ['manufacturer', 'distributor', 'broker', 'importer']
const CUSTOMER_TYPES = ['retail', 'wholesale', 'distributor', 'ecommerce', 'government', 'internal']

// ─── Productos ────────────────────────────────────────────
function ProductsTab() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)

  // Form state
  const [sku, setSku] = useState('')
  const [name, setName] = useState('')
  const [uom, setUom] = useState('UN')
  const [gtin13, setGtin13] = useState('')
  const [traceability, setTraceability] = useState('none')
  const [storageCondition, setStorageCondition] = useState('ambient')
  const [rotation, setRotation] = useState('FEFO')
  const [weight, setWeight] = useState('')
  const [volume, setVolume] = useState('')
  const [shelfLife, setShelfLife] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['products', page, search],
    queryFn: () => masterApi.getProducts({ page, page_size: PAGE_SIZE, search: search || undefined }),
    placeholderData: prev => prev,
  })

  const reset = () => {
    setSku(''); setName(''); setUom('UN'); setGtin13(''); setTraceability('none')
    setStorageCondition('ambient'); setRotation('FEFO'); setWeight(''); setVolume(''); setShelfLife('')
    setEditing(null)
  }

  const openCreate = () => { reset(); setOpen(true) }
  const openEdit = (p: Product) => {
    setEditing(p)
    setSku(p.sku); setName(p.name); setUom(p.uom)
    setGtin13((p as any).gtin_13 ?? '')
    setTraceability((p as any).traceability_type ?? 'none')
    setStorageCondition((p as any).storage_condition ?? 'ambient')
    setRotation((p as any).rotation_strategy ?? 'FEFO')
    setWeight((p as any).weight_kg != null ? String((p as any).weight_kg) : '')
    setVolume((p as any).volume_m3 != null ? String((p as any).volume_m3) : '')
    setShelfLife((p as any).shelf_life_days != null ? String((p as any).shelf_life_days) : '')
    setOpen(true)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        sku, name, uom,
        gtin_13: gtin13 || undefined,
        traceability_type: traceability,
        storage_condition: storageCondition,
        rotation_strategy: rotation,
        weight_kg: weight ? Number(weight) : undefined,
        volume_m3: volume ? Number(volume) : undefined,
        shelf_life_days: shelfLife ? Number(shelfLife) : undefined,
      }
      return editing
        ? masterApi.updateProduct(editing.id, payload)
        : masterApi.createProduct(payload)
    },
    onSuccess: () => {
      toast.success(editing ? 'Producto actualizado' : 'Producto creado')
      qc.invalidateQueries({ queryKey: ['products'] })
      setOpen(false); reset()
    },
    onError: () => toast.error('No se pudo guardar el producto'),
  })

  const canSave = sku.trim().length > 0 && name.trim().length > 0 && uom.trim().length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{data?.total ?? 0} productos</p>
        <div className="flex gap-2">
          <div className="flex items-center gap-2 h-9 border border-gray-300 rounded-lg px-3 text-sm">
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por SKU o nombre…"
              className="outline-none placeholder:text-gray-400 w-48"
            />
            {search && (
              <button onClick={() => { setSearch(''); setPage(1) }} className="text-gray-400 hover:text-gray-600">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" /> Nuevo Producto
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>SKU</Th>
              <Th>Nombre</Th>
              <Th>UOM</Th>
              <Th>GTIN-13</Th>
              <Th>Trazabilidad</Th>
              <Th>Almacenamiento</Th>
              <Th>Estado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 8 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={8} message="No hay productos registrados" />
            ) : (
              data.items.map(p => (
                <Tr key={p.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{p.sku}</span></Td>
                  <Td className="font-medium text-gray-900">{p.name}</Td>
                  <Td className="text-xs text-gray-500">{p.uom}</Td>
                  <Td className="text-xs font-mono text-gray-400">{p.gtin_13 ?? '—'}</Td>
                  <Td className="text-xs text-gray-500 capitalize">{(p as any).traceability_type?.replace(/_/g, ' ') ?? '—'}</Td>
                  <Td className="text-xs text-gray-500 capitalize">{(p as any).storage_condition?.replace(/_/g, ' ') ?? '—'}</Td>
                  <Td><Badge status={p.status} /></Td>
                  <Td>
                    <button onClick={() => openEdit(p)} title="Editar"
                      className="text-gray-500 hover:text-primary-700 transition-colors">
                      <Pencil className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={open}
        onClose={() => { setOpen(false); reset() }}
        title={editing ? `Editar producto ${editing.sku}` : 'Nuevo producto'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => { setOpen(false); reset() }}>Cancelar</Button>
            <Button size="sm" disabled={!canSave} loading={saveMut.isPending}
              onClick={() => saveMut.mutate()}>
              {editing ? 'Guardar cambios' : 'Crear producto'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Input label="SKU *" value={sku} onChange={e => setSku(e.target.value)}
              placeholder="Código único del producto" disabled={!!editing} />
            <div className="sm:col-span-2">
              <Input label="Nombre *" value={name} onChange={e => setName(e.target.value)}
                placeholder="Nombre comercial del producto" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Input label="Unidad de medida *" value={uom} onChange={e => setUom(e.target.value)}
              placeholder="UN, KG, LT, CJ…" />
            <Input label="GTIN-13 / EAN" value={gtin13} onChange={e => setGtin13(e.target.value)}
              placeholder="Código de barras (opcional)" />
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Trazabilidad</label>
              <select value={traceability} onChange={e => setTraceability(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {TRACEABILITY_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Condición de almacenamiento</label>
              <select value={storageCondition} onChange={e => setStorageCondition(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {STORAGE_CONDITIONS.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Estrategia de rotación</label>
              <select value={rotation} onChange={e => setRotation(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
                {ROTATION_STRATEGIES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <Input label="Vida útil (días)" type="number" value={shelfLife}
              onChange={e => setShelfLife(e.target.value)} placeholder="Opcional" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Peso (kg)" type="number" step="0.001" value={weight}
              onChange={e => setWeight(e.target.value)} placeholder="Opcional" />
            <Input label="Volumen (m³)" type="number" step="0.001" value={volume}
              onChange={e => setVolume(e.target.value)} placeholder="Opcional" />
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Proveedores ──────────────────────────────────────────
function SuppliersTab() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Supplier | null>(null)

  const [code, setCode] = useState('')
  const [supplierName, setSupplierName] = useState('')
  const [supplierType, setSupplierType] = useState('distributor')
  const [contactEmail, setContactEmail] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [leadTime, setLeadTime] = useState('')
  const [country, setCountry] = useState('PA')
  const [taxId, setTaxId] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['suppliers', page, search],
    queryFn: () => masterApi.getSuppliers({ page, page_size: PAGE_SIZE, search: search || undefined }),
    placeholderData: prev => prev,
  })

  const reset = () => {
    setCode(''); setSupplierName(''); setSupplierType('distributor'); setContactEmail('')
    setContactPhone(''); setLeadTime(''); setCountry('PA'); setTaxId('')
    setEditing(null)
  }

  const openCreate = () => { reset(); setOpen(true) }
  const openEdit = (s: Supplier) => {
    setEditing(s)
    setCode(s.code); setSupplierName(s.name); setSupplierType(s.supplier_type)
    setContactEmail((s as any).contact_email ?? '')
    setContactPhone((s as any).contact_phone ?? '')
    setLeadTime(s.lead_time_days != null ? String(s.lead_time_days) : '')
    setCountry((s as any).country ?? 'PA')
    setTaxId((s as any).tax_id ?? '')
    setOpen(true)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        code, name: supplierName, supplier_type: supplierType,
        contact_email: contactEmail || undefined,
        contact_phone: contactPhone || undefined,
        lead_time_days: leadTime ? Number(leadTime) : undefined,
        country: country || undefined,
        tax_id: taxId || undefined,
      }
      return editing
        ? masterApi.updateSupplier(editing.id, payload)
        : masterApi.createSupplier(payload)
    },
    onSuccess: () => {
      toast.success(editing ? 'Proveedor actualizado' : 'Proveedor creado')
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      setOpen(false); reset()
    },
    onError: () => toast.error('No se pudo guardar el proveedor'),
  })

  const canSave = code.trim().length > 0 && supplierName.trim().length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{data?.total ?? 0} proveedores</p>
        <div className="flex gap-2">
          <div className="flex items-center gap-2 h-9 border border-gray-300 rounded-lg px-3 text-sm">
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por código o nombre…"
              className="outline-none placeholder:text-gray-400 w-48"
            />
            {search && (
              <button onClick={() => { setSearch(''); setPage(1) }} className="text-gray-400 hover:text-gray-600">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" /> Nuevo Proveedor
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Código</Th>
              <Th>Nombre</Th>
              <Th>Tipo</Th>
              <Th>Contacto</Th>
              <Th>Lead Time</Th>
              <Th>País</Th>
              <Th>Estado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 8 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={8} message="No hay proveedores registrados" />
            ) : (
              data.items.map(s => (
                <Tr key={s.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{s.code}</span></Td>
                  <Td className="font-medium text-gray-900">{s.name}</Td>
                  <Td className="text-xs text-gray-500 capitalize">{s.supplier_type}</Td>
                  <Td className="text-xs text-gray-500">{(s as any).contact_email ?? '—'}</Td>
                  <Td className="text-xs text-gray-500">
                    {s.lead_time_days != null ? `${s.lead_time_days} días` : '—'}
                  </Td>
                  <Td className="text-xs text-gray-500">{(s as any).country ?? '—'}</Td>
                  <Td><Badge status={s.status} /></Td>
                  <Td>
                    <button onClick={() => openEdit(s)} title="Editar"
                      className="text-gray-500 hover:text-primary-700 transition-colors">
                      <Pencil className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={open}
        onClose={() => { setOpen(false); reset() }}
        title={editing ? `Editar proveedor ${editing.code}` : 'Nuevo proveedor'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => { setOpen(false); reset() }}>Cancelar</Button>
            <Button size="sm" disabled={!canSave} loading={saveMut.isPending}
              onClick={() => saveMut.mutate()}>
              {editing ? 'Guardar cambios' : 'Crear proveedor'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Código *" value={code} onChange={e => setCode(e.target.value)}
              placeholder="Código único del proveedor" disabled={!!editing} />
            <Input label="Nombre *" value={supplierName} onChange={e => setSupplierName(e.target.value)}
              placeholder="Nombre legal del proveedor" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Tipo de proveedor</label>
              <select value={supplierType} onChange={e => setSupplierType(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {SUPPLIER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <Input label="RUC / NIT / Tax ID" value={taxId} onChange={e => setTaxId(e.target.value)}
              placeholder="Identificación tributaria (opcional)" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Email de contacto" type="email" value={contactEmail}
              onChange={e => setContactEmail(e.target.value)} placeholder="contacto@proveedor.com" />
            <Input label="Teléfono de contacto" value={contactPhone}
              onChange={e => setContactPhone(e.target.value)} placeholder="+507 000-0000" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Lead time (días)" type="number" value={leadTime}
              onChange={e => setLeadTime(e.target.value)} placeholder="Días promedio de entrega" />
            <Input label="País" value={country} onChange={e => setCountry(e.target.value)}
              placeholder="PA, CO, US…" />
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Clientes ─────────────────────────────────────────────
function CustomersTab() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Customer | null>(null)

  const [code, setCode] = useState('')
  const [customerName, setCustomerName] = useState('')
  const [customerType, setCustomerType] = useState('retail')
  const [contactEmail, setContactEmail] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [deliveryCity, setDeliveryCity] = useState('')
  const [country, setCountry] = useState('PA')
  const [ruc, setRuc] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['customers', page, search],
    queryFn: () => masterApi.getCustomers({ page, page_size: PAGE_SIZE, search: search || undefined }),
    placeholderData: prev => prev,
  })

  const reset = () => {
    setCode(''); setCustomerName(''); setCustomerType('retail'); setContactEmail('')
    setContactPhone(''); setDeliveryCity(''); setCountry('PA'); setRuc('')
    setEditing(null)
  }

  const openCreate = () => { reset(); setOpen(true) }
  const openEdit = (c: Customer) => {
    setEditing(c)
    setCode(c.code); setCustomerName(c.name); setCustomerType(c.customer_type)
    setContactEmail(c.contact_email ?? '')
    setContactPhone((c as any).contact_phone ?? '')
    setDeliveryCity(c.delivery_city ?? '')
    setCountry((c as any).delivery_country ?? 'PA')
    setRuc((c as any).ruc ?? '')
    setOpen(true)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        code, name: customerName, customer_type: customerType,
        contact_email: contactEmail || undefined,
        contact_phone: contactPhone || undefined,
        delivery_city: deliveryCity || undefined,
        delivery_country: country || undefined,
        ruc: ruc || undefined,
      }
      return editing
        ? masterApi.updateCustomer(editing.id, payload)
        : masterApi.createCustomer(payload)
    },
    onSuccess: () => {
      toast.success(editing ? 'Cliente actualizado' : 'Cliente creado')
      qc.invalidateQueries({ queryKey: ['customers'] })
      setOpen(false); reset()
    },
    onError: () => toast.error('No se pudo guardar el cliente'),
  })

  const canSave = code.trim().length > 0 && customerName.trim().length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{data?.total ?? 0} clientes</p>
        <div className="flex gap-2">
          <div className="flex items-center gap-2 h-9 border border-gray-300 rounded-lg px-3 text-sm">
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por código o nombre…"
              className="outline-none placeholder:text-gray-400 w-48"
            />
            {search && (
              <button onClick={() => { setSearch(''); setPage(1) }} className="text-gray-400 hover:text-gray-600">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" /> Nuevo Cliente
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Código</Th>
              <Th>Nombre</Th>
              <Th>Tipo</Th>
              <Th>Contacto</Th>
              <Th>Ciudad</Th>
              <Th>Estado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 7 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={7} message="No hay clientes registrados" />
            ) : (
              data.items.map(c => (
                <Tr key={c.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{c.code}</span></Td>
                  <Td className="font-medium text-gray-900">{c.name}</Td>
                  <Td className="text-xs text-gray-500 capitalize">{c.customer_type}</Td>
                  <Td className="text-xs text-gray-500">{c.contact_email ?? '—'}</Td>
                  <Td className="text-xs text-gray-500">{c.delivery_city ?? '—'}</Td>
                  <Td><Badge status={c.is_active ? 'active' : 'inactive'} /></Td>
                  <Td>
                    <button onClick={() => openEdit(c)} title="Editar"
                      className="text-gray-500 hover:text-primary-700 transition-colors">
                      <Pencil className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={open}
        onClose={() => { setOpen(false); reset() }}
        title={editing ? `Editar cliente ${editing.code}` : 'Nuevo cliente'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => { setOpen(false); reset() }}>Cancelar</Button>
            <Button size="sm" disabled={!canSave} loading={saveMut.isPending}
              onClick={() => saveMut.mutate()}>
              {editing ? 'Guardar cambios' : 'Crear cliente'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Código *" value={code} onChange={e => setCode(e.target.value)}
              placeholder="Código único del cliente" disabled={!!editing} />
            <Input label="Nombre *" value={customerName} onChange={e => setCustomerName(e.target.value)}
              placeholder="Nombre o razón social del cliente" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Tipo de cliente</label>
              <select value={customerType} onChange={e => setCustomerType(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
                {CUSTOMER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <Input label="RUC / Tax ID" value={ruc} onChange={e => setRuc(e.target.value)}
              placeholder="Identificación tributaria (opcional)" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Email de contacto" type="email" value={contactEmail}
              onChange={e => setContactEmail(e.target.value)} placeholder="contacto@cliente.com" />
            <Input label="Teléfono de contacto" value={contactPhone}
              onChange={e => setContactPhone(e.target.value)} placeholder="+507 000-0000" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Ciudad de entrega" value={deliveryCity} onChange={e => setDeliveryCity(e.target.value)}
              placeholder="Ciudad principal de entrega" />
            <Input label="País" value={country} onChange={e => setCountry(e.target.value)}
              placeholder="PA, CO, US…" />
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Tipos de caja ────────────────────────────────────────
function BoxTypesTab() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<BoxType | null>(null)

  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [length, setLength] = useState('')
  const [width, setWidth] = useState('')
  const [height, setHeight] = useState('')
  const [maxWeight, setMaxWeight] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['box-types', page, search],
    queryFn: () => masterApi.getBoxTypes({ page, page_size: PAGE_SIZE, search: search || undefined }),
    placeholderData: prev => prev,
  })

  const reset = () => {
    setCode(''); setName(''); setDescription('')
    setLength(''); setWidth(''); setHeight(''); setMaxWeight('')
    setEditing(null)
  }

  const openCreate = () => { reset(); setOpen(true) }
  const openEdit = (b: BoxType) => {
    setEditing(b)
    setCode(b.code); setName(b.name); setDescription(b.description ?? '')
    setLength(b.length_cm != null ? String(b.length_cm) : '')
    setWidth(b.width_cm != null ? String(b.width_cm) : '')
    setHeight(b.height_cm != null ? String(b.height_cm) : '')
    setMaxWeight(b.max_weight_kg != null ? String(b.max_weight_kg) : '')
    setOpen(true)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        code, name, description: description || undefined,
        length_cm: length ? Number(length) : undefined,
        width_cm: width ? Number(width) : undefined,
        height_cm: height ? Number(height) : undefined,
        max_weight_kg: maxWeight ? Number(maxWeight) : undefined,
      }
      return editing
        ? masterApi.updateBoxType(editing.id, payload)
        : masterApi.createBoxType(payload)
    },
    onSuccess: () => {
      toast.success(editing ? 'Tipo de caja actualizado' : 'Tipo de caja creado')
      qc.invalidateQueries({ queryKey: ['box-types'] })
      setOpen(false); reset()
    },
    onError: () => toast.error('No se pudo guardar el tipo de caja'),
  })

  const canSave = code.trim().length > 0 && name.trim().length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{data?.total ?? 0} tipos de caja</p>
        <div className="flex gap-2">
          <div className="flex items-center gap-2 h-9 border border-gray-300 rounded-lg px-3 text-sm">
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por código o nombre…"
              className="outline-none placeholder:text-gray-400 w-48"
            />
            {search && (
              <button onClick={() => { setSearch(''); setPage(1) }} className="text-gray-400 hover:text-gray-600">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" /> Nuevo Tipo de Caja
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Código</Th>
              <Th>Nombre</Th>
              <Th>Dimensiones (L×A×A cm)</Th>
              <Th>Peso máx. (kg)</Th>
              <Th>Estado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 6 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={6} message="No hay tipos de caja registrados" />
            ) : (
              data.items.map(b => (
                <Tr key={b.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{b.code}</span></Td>
                  <Td className="font-medium text-gray-900">{b.name}</Td>
                  <Td className="text-xs text-gray-500">
                    {b.length_cm != null || b.width_cm != null || b.height_cm != null
                      ? `${b.length_cm ?? '—'} × ${b.width_cm ?? '—'} × ${b.height_cm ?? '—'}`
                      : '—'}
                  </Td>
                  <Td className="text-xs text-gray-500">{b.max_weight_kg ?? '—'}</Td>
                  <Td><Badge status={b.is_active ? 'active' : 'inactive'} /></Td>
                  <Td>
                    <button onClick={() => openEdit(b)} title="Editar"
                      className="text-gray-500 hover:text-primary-700 transition-colors">
                      <Pencil className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={open}
        onClose={() => { setOpen(false); reset() }}
        title={editing ? `Editar tipo de caja ${editing.code}` : 'Nuevo tipo de caja'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => { setOpen(false); reset() }}>Cancelar</Button>
            <Button size="sm" disabled={!canSave} loading={saveMut.isPending}
              onClick={() => saveMut.mutate()}>
              {editing ? 'Guardar cambios' : 'Crear tipo de caja'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Código *" value={code} onChange={e => setCode(e.target.value)}
              placeholder="Ej: CARTON_M" disabled={!!editing} />
            <Input label="Nombre *" value={name} onChange={e => setName(e.target.value)}
              placeholder="Ej: Cartón mediano" />
          </div>
          <Input label="Descripción" value={description} onChange={e => setDescription(e.target.value)}
            placeholder="Opcional" />
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <Input label="Largo (cm)" type="number" value={length}
              onChange={e => setLength(e.target.value)} placeholder="Opcional" />
            <Input label="Ancho (cm)" type="number" value={width}
              onChange={e => setWidth(e.target.value)} placeholder="Opcional" />
            <Input label="Alto (cm)" type="number" value={height}
              onChange={e => setHeight(e.target.value)} placeholder="Opcional" />
            <Input label="Peso máx. (kg)" type="number" value={maxWeight}
              onChange={e => setMaxWeight(e.target.value)} placeholder="Opcional" />
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Ubicaciones ──────────────────────────────────────────
function LocationsTab() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [warehouseFilter, setWarehouseFilter] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<LocationLite | null>(null)

  const [locCode, setLocCode] = useState('')
  const [locWarehouseId, setLocWarehouseId] = useState('')
  const [locType, setLocType] = useState('standard')
  const [aisle, setAisle] = useState('')
  const [bay, setBay] = useState('')
  const [level, setLevel] = useState('')
  const [position, setPosition] = useState('')
  const [maxWeight, setMaxWeight] = useState('')
  const [maxVolume, setMaxVolume] = useState('')

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const { data, isLoading } = useQuery({
    queryKey: ['locations', page, search, warehouseFilter],
    queryFn: () => masterApi.getLocations({
      page, page_size: PAGE_SIZE,
      search: search || undefined,
      warehouse_id: warehouseFilter || undefined,
    }),
    placeholderData: prev => prev,
  })

  const reset = () => {
    setLocCode(''); setLocWarehouseId(''); setLocType('standard')
    setAisle(''); setBay(''); setLevel(''); setPosition('')
    setMaxWeight(''); setMaxVolume(''); setEditing(null)
  }

  const openCreate = () => { reset(); setOpen(true) }
  const openEdit = (l: LocationLite) => {
    setEditing(l)
    setLocCode(l.code); setLocWarehouseId(l.warehouse_id); setLocType(l.location_type)
    setAisle((l as any).aisle ?? ''); setBay((l as any).bay ?? '')
    setLevel((l as any).level ?? ''); setPosition((l as any).position ?? '')
    setMaxWeight((l as any).max_weight_kg != null ? String((l as any).max_weight_kg) : '')
    setMaxVolume((l as any).max_volume_m3 != null ? String((l as any).max_volume_m3) : '')
    setOpen(true)
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = {
        code: locCode,
        warehouse_id: locWarehouseId,
        location_type: locType,
        aisle: aisle || undefined,
        bay: bay || undefined,
        level: level || undefined,
        position: position || undefined,
        max_weight_kg: maxWeight ? Number(maxWeight) : undefined,
        max_volume_m3: maxVolume ? Number(maxVolume) : undefined,
      }
      return editing
        ? masterApi.updateLocation(editing.id, payload)
        : masterApi.createLocation(payload)
    },
    onSuccess: () => {
      toast.success(editing ? 'Ubicación actualizada' : 'Ubicación creada')
      qc.invalidateQueries({ queryKey: ['locations'] })
      setOpen(false); reset()
    },
    onError: () => toast.error('No se pudo guardar la ubicación'),
  })

  const canSave = locCode.trim().length > 0 && locWarehouseId.length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{data?.total ?? 0} ubicaciones</p>
        <div className="flex gap-2">
          <select
            value={warehouseFilter}
            onChange={e => { setWarehouseFilter(e.target.value); setPage(1) }}
            className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
          >
            <option value="">Todas las bodegas</option>
            {warehouses?.items.map(w => (
              <option key={w.id} value={w.id}>{w.code} — {w.name}</option>
            ))}
          </select>
          <div className="flex items-center gap-2 h-9 border border-gray-300 rounded-lg px-3 text-sm">
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Buscar por código…"
              className="outline-none placeholder:text-gray-400 w-36"
            />
            {search && (
              <button onClick={() => { setSearch(''); setPage(1) }} className="text-gray-400 hover:text-gray-600">
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" /> Nueva Ubicación
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <Table>
          <Thead>
            <Tr>
              <Th>Código</Th>
              <Th>Bodega</Th>
              <Th>Tipo</Th>
              <Th>Pasillo</Th>
              <Th>Bahía</Th>
              <Th>Nivel</Th>
              <Th>Estado</Th>
              <Th>Acciones</Th>
            </Tr>
          </Thead>
          <Tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Tr key={i}>{Array.from({ length: 8 }).map((_, j) => (
                  <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                ))}</Tr>
              ))
            ) : !data?.items.length ? (
              <EmptyRow cols={8} message="No hay ubicaciones registradas" />
            ) : (
              data.items.map(l => (
                <Tr key={l.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{l.code}</span></Td>
                  <Td className="text-xs text-gray-500">
                    {warehouses?.items.find(w => w.id === l.warehouse_id)?.code ?? l.warehouse_id.slice(0, 8)}
                  </Td>
                  <Td className="text-xs text-gray-500 capitalize">{l.location_type.replace(/_/g, ' ')}</Td>
                  <Td className="text-xs text-gray-400">{(l as any).aisle ?? '—'}</Td>
                  <Td className="text-xs text-gray-400">{(l as any).bay ?? '—'}</Td>
                  <Td className="text-xs text-gray-400">{(l as any).level ?? '—'}</Td>
                  <Td><Badge status={l.status} /></Td>
                  <Td>
                    <button onClick={() => openEdit(l)} title="Editar"
                      className="text-gray-500 hover:text-primary-700 transition-colors">
                      <Pencil className="h-4 w-4" />
                    </button>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
      </Card>

      <Modal
        open={open}
        onClose={() => { setOpen(false); reset() }}
        title={editing ? `Editar ubicación ${editing.code}` : 'Nueva ubicación'}
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => { setOpen(false); reset() }}>Cancelar</Button>
            <Button size="sm" disabled={!canSave} loading={saveMut.isPending}
              onClick={() => saveMut.mutate()}>
              {editing ? 'Guardar cambios' : 'Crear ubicación'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Código *" value={locCode} onChange={e => setLocCode(e.target.value)}
              placeholder="Ej: A-01-B-05" disabled={!!editing} />
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Bodega *</label>
              <select value={locWarehouseId} onChange={e => setLocWarehouseId(e.target.value)}
                className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm"
                disabled={!!editing}>
                <option value="">Seleccionar…</option>
                {warehouses?.items.map(w => (
                  <option key={w.id} value={w.id}>{w.code} — {w.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Tipo de ubicación</label>
            <select value={locType} onChange={e => setLocType(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm capitalize">
              {LOCATION_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Input label="Pasillo" value={aisle} onChange={e => setAisle(e.target.value)} placeholder="A, B, C…" />
            <Input label="Bahía" value={bay} onChange={e => setBay(e.target.value)} placeholder="01, 02…" />
            <Input label="Nivel" value={level} onChange={e => setLevel(e.target.value)} placeholder="1, 2, 3…" />
            <Input label="Posición" value={position} onChange={e => setPosition(e.target.value)} placeholder="L, R, C…" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label="Peso máximo (kg)" type="number" value={maxWeight}
              onChange={e => setMaxWeight(e.target.value)} placeholder="Opcional" />
            <Input label="Volumen máximo (m³)" type="number" value={maxVolume}
              onChange={e => setMaxVolume(e.target.value)} placeholder="Opcional" />
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ─── Página Principal ─────────────────────────────────────
const PATH_TO_TAB: Record<string, Tab> = {
  '/master/products': 'productos',
  '/master/suppliers': 'proveedores',
  '/master/customers': 'clientes',
  '/master/box-types': 'tipos-caja',
  '/master/locations': 'ubicaciones',
}

const TAB_TO_PATH: Record<Tab, string> = {
  productos: '/master/products',
  proveedores: '/master/suppliers',
  clientes: '/master/customers',
  'tipos-caja': '/master/box-types',
  ubicaciones: '/master/locations',
}

export function MasterDataPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const activeTab: Tab = PATH_TO_TAB[location.pathname] ?? 'productos'

  const tabs: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: 'productos', label: 'Productos', icon: Package },
    { id: 'proveedores', label: 'Proveedores', icon: Users },
    { id: 'clientes', label: 'Clientes', icon: UserCheck },
    { id: 'tipos-caja', label: 'Tipos de Caja', icon: Box },
    { id: 'ubicaciones', label: 'Ubicaciones', icon: MapPin },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Maestros de Datos</h1>
        <p className="text-sm text-gray-500 mt-1">
          Gestión de productos, proveedores, clientes, tipos de caja y ubicaciones del almacén.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-6" aria-label="Tabs">
          {tabs.map(tab => {
            const isActive = activeTab === tab.id
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => navigate(TAB_TO_PATH[tab.id])}
                className={`
                  group inline-flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm
                  ${isActive
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }
                `}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-primary-600' : 'text-gray-400 group-hover:text-gray-500'}`} />
                {tab.label}
              </button>
            )
          })}
        </nav>
      </div>

      <div className="pt-2">
        {activeTab === 'productos' && <ProductsTab />}
        {activeTab === 'proveedores' && <SuppliersTab />}
        {activeTab === 'clientes' && <CustomersTab />}
        {activeTab === 'tipos-caja' && <BoxTypesTab />}
        {activeTab === 'ubicaciones' && <LocationsTab />}
      </div>
    </div>
  )
}
