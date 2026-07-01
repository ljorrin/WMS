import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  User as UserIcon, KeyRound, Warehouse as WarehouseIcon,
  ShieldCheck, Plug, CheckCircle2, AlertCircle, Building2, BookOpen,
  Plus, Trash2, Lock,
} from 'lucide-react'
import { authApi, warehouseApi, integrationsApi } from '@/api/endpoints'
import { useAuthStore } from '@/store/authStore'
import { useReasonCodes } from '@/hooks/useReasonCodes'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import toast from 'react-hot-toast'

export function SettingsPage() {
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<'perfil' | 'bodegas' | 'integraciones' | 'nomencladores'>('perfil')

  // Gestión de razones de ajuste
  const { all: reasonCodes, addCode, removeCode } = useReasonCodes()
  const [newCode, setNewCode] = useState('')
  const [newLabel, setNewLabel] = useState('')

  const handleAddCode = () => {
    const ok = addCode(newCode, newLabel)
    if (!ok) {
      toast.error('Ese código ya existe en la lista')
      return
    }
    toast.success(`Código "${newCode.toUpperCase().trim()}" agregado`)
    setNewCode(''); setNewLabel('')
  }

  const alreadyExists = newCode.trim().length > 0 &&
    reasonCodes.some(c => c.code === newCode.trim().toUpperCase().replace(/\s+/g, '_'))

  // -- Profile & Security --
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')

  const changePwdMut = useMutation({
    mutationFn: () => authApi.changePassword(currentPwd, newPwd),
    onSuccess: () => {
      toast.success('Contraseña actualizada')
      setCurrentPwd(''); setNewPwd(''); setConfirmPwd('')
    },
    onError: () => toast.error('No se pudo actualizar la contraseña'),
  })
  const pwdValid = currentPwd.length >= 1 && newPwd.length >= 8 && newPwd === confirmPwd

  // -- Warehouses --
  const { data: warehouses, isLoading: whLoading } = useQuery({
    queryKey: ['warehouses', 'settings'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
    enabled: activeTab === 'bodegas'
  })

  // -- Integrations --
  const { data: integrations, isLoading: intLoading } = useQuery({
    queryKey: ['integrations', 'status'],
    queryFn: () => integrationsApi.getStatus(),
    enabled: activeTab === 'integraciones'
  })

  // Integration human names
  const integrationNames: Record<string, string> = {
    erp: 'ERP (SAP/Odoo)',
    ecommerce: 'eCommerce (Shopify/VTEX)',
    carrier: 'Transporte (DHL/FedEx)',
    siga: 'Aduanas Panamá (ANA/SIGA)',
    dgi: 'Facturación Electrónica (DGI)',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Configuración del Sistema</h1>
        <p className="text-sm text-gray-500 mt-1">
          Gestiona tu perfil, seguridad, bodegas operativas y estado de integraciones del WMS.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-6" aria-label="Tabs">
          {[
            { id: 'perfil', name: 'Perfil y Seguridad', icon: UserIcon },
            { id: 'bodegas', name: 'Bodegas', icon: WarehouseIcon },
            { id: 'integraciones', name: 'Integraciones', icon: Plug },
            { id: 'nomencladores', name: 'Nomencladores (Diccionarios)', icon: BookOpen },
          ].map((tab) => {
            const isActive = activeTab === tab.id
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`
                  group inline-flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm
                  ${isActive 
                    ? 'border-primary-600 text-primary-600' 
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }
                `}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-primary-600' : 'text-gray-400 group-hover:text-gray-500'}`} />
                {tab.name}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Content */}
      <div className="pt-2">
        
        {/* --- PERFIL Y SEGURIDAD --- */}
        {activeTab === 'perfil' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <UserIcon className="h-5 w-5 text-gray-400" /> Datos del Usuario
                </CardTitle>
              </CardHeader>
              <div className="flex flex-col gap-3 text-sm px-1">
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Nombre Completo</span>
                  <span className="font-medium text-gray-900">{user?.full_name ?? '—'}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Nombre de Usuario</span>
                  <span className="font-mono text-gray-700 bg-gray-50 px-1 rounded">{user?.username ?? '—'}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Correo Electrónico</span>
                  <span className="text-gray-700">{user?.email ?? '—'}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Estado de Cuenta</span>
                  <Badge status={user?.is_active ? 'active' : 'inactive'}
                    label={user?.is_active ? 'Activo' : 'Inactivo'} />
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500 flex items-center gap-1">
                    <Building2 className="h-4 w-4" /> Tenant ID
                  </span>
                  <span className="text-gray-600 font-mono text-xs" title={user?.tenant_id}>{user?.tenant_id ? (user.tenant_id.slice(0,8) + '...') : '—'}</span>
                </div>
                <div className="py-2">
                  <span className="text-gray-500 flex items-center gap-1 mb-2 font-medium">
                    <ShieldCheck className="h-4 w-4" /> Roles Asignados
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {user?.roles?.length
                      ? user.roles.map((r: any) => <Badge key={r.id || r} status="confirmed" label={typeof r === 'string' ? r : r.name} />)
                      : <span className="text-gray-400 italic">Sin roles asignados</span>}
                  </div>
                </div>
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <KeyRound className="h-5 w-5 text-gray-400" /> Cambiar Contraseña
                </CardTitle>
              </CardHeader>
              <div className="space-y-4">
                <Input label="Contraseña actual" type="password" value={currentPwd}
                  onChange={e => setCurrentPwd(e.target.value)} placeholder="••••••••" />
                <Input label="Nueva contraseña" type="password" value={newPwd}
                  onChange={e => setNewPwd(e.target.value)} placeholder="Mínimo 8 caracteres"
                  error={newPwd.length > 0 && newPwd.length < 8 ? 'Mínimo 8 caracteres' : undefined} />
                <Input label="Confirmar nueva contraseña" type="password" value={confirmPwd}
                  onChange={e => setConfirmPwd(e.target.value)} placeholder="Repite la contraseña"
                  error={confirmPwd.length > 0 && confirmPwd !== newPwd ? 'No coincide' : undefined} />
                <div className="pt-2">
                  <Button size="sm" disabled={!pwdValid} loading={changePwdMut.isPending}
                    onClick={() => changePwdMut.mutate()}>
                    Actualizar contraseña
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* --- BODEGAS --- */}
        {activeTab === 'bodegas' && (
          <Card padding={false}>
            <div className="px-5 py-4 border-b border-gray-100">
              <CardTitle className="flex items-center gap-2 text-lg">
                <WarehouseIcon className="h-5 w-5 text-gray-400" /> Bodegas Configuradas ({warehouses?.total ?? 0})
              </CardTitle>
            </div>
            <Table>
              <Thead>
                <Tr>
                  <Th>Código</Th>
                  <Th>Nombre</Th>
                  <Th>Tipo</Th>
                  <Th>Ciudad</Th>
                  <Th>Cadena de Frío</Th>
                  <Th>Estrategia de Picking</Th>
                  <Th>Estado</Th>
                </Tr>
              </Thead>
              <Tbody>
                {whLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <Tr key={i}>
                      {Array.from({ length: 7 }).map((_, j) => (
                        <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-20" /></Td>
                      ))}
                    </Tr>
                  ))
                ) : !warehouses?.items.length ? (
                  <EmptyRow cols={7} message="No hay bodegas configuradas en el sistema" />
                ) : (
                  warehouses.items.map(w => (
                    <Tr key={w.id}>
                      <Td><span className="font-mono font-medium text-primary-700">{w.code}</span></Td>
                      <Td className="font-medium text-gray-900">{w.name}</Td>
                      <Td className="text-xs text-gray-500 capitalize">{w.type?.replace(/_/g, ' ')}</Td>
                      <Td className="text-gray-600">{w.city ?? '—'}</Td>
                      <Td>
                        {w.has_cold_storage
                          ? <Badge status="in_transit" label="Sí" />
                          : <span className="text-xs text-gray-400">No</span>}
                      </Td>
                      <Td className="text-xs text-gray-500 capitalize">{w.picking_strategy?.replace(/_/g, ' ')}</Td>
                      <Td><Badge status={w.status} /></Td>
                    </Tr>
                  ))
                )}
              </Tbody>
            </Table>
          </Card>
        )}

        {/* --- INTEGRACIONES --- */}
        {activeTab === 'integraciones' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {intLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Card key={i}>
                  <div className="h-24 bg-gray-50 animate-pulse rounded-md" />
                </Card>
              ))
            ) : integrations ? (
              Object.entries(integrations).map(([key, data]) => (
                <Card key={key} className={data.configured ? 'border-green-100 shadow-sm' : ''}>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span className="text-base">{integrationNames[key] || key}</span>
                      {data.configured ? (
                        <CheckCircle2 className="h-5 w-5 text-green-500" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-amber-500" />
                      )}
                    </CardTitle>
                  </CardHeader>
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Badge 
                        status={data.configured ? 'active' : 'pending'} 
                        label={data.configured ? 'Conectado' : 'Requiere Configuración'} 
                      />
                    </div>
                    
                    {!data.configured && data.missing?.length > 0 && (
                      <div className="bg-amber-50 p-3 rounded-md border border-amber-100">
                        <p className="text-xs font-medium text-amber-800 mb-2">Variables de entorno faltantes:</p>
                        <ul className="list-disc list-inside text-xs text-amber-700 space-y-1">
                          {data.missing.map(m => (
                            <li key={m} className="font-mono">{m}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {data.configured && (
                      <p className="text-sm text-gray-600">
                        La integración está activa y lista para operar.
                      </p>
                    )}
                  </div>
                </Card>
              ))
            ) : (
              <div className="col-span-full py-8 text-center text-gray-500">
                No se pudo cargar el estado de las integraciones.
              </div>
            )}
          </div>
        )}

        {/* --- NOMENCLADORES (DICCIONARIOS) --- */}
        {activeTab === 'nomencladores' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-primary-500" /> Estrategias de Picking
                </CardTitle>
              </CardHeader>
              <div className="text-sm">
                <table className="w-full">
                  <tbody className="divide-y divide-gray-100">
                    <tr><td className="py-2 font-mono text-xs text-gray-600">discrete</td><td className="py-2 text-gray-800">1 orden 1 operador</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">batch</td><td className="py-2 text-gray-800">Múltiples órdenes, 1 operador</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">zone</td><td className="py-2 text-gray-800">Por zonas del almacén</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">cluster</td><td className="py-2 text-gray-800">Carros de picking múltiples</td></tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-primary-500" /> Condiciones de Almacenamiento
                </CardTitle>
              </CardHeader>
              <div className="text-sm">
                <table className="w-full">
                  <tbody className="divide-y divide-gray-100">
                    <tr><td className="py-2 font-mono text-xs text-gray-600">ambient</td><td className="py-2 text-gray-800">Temperatura ambiente</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">controlled</td><td className="py-2 text-gray-800">Controlada (15-25°C)</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">refrigerated</td><td className="py-2 text-gray-800">Refrigerado (2-8°C)</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">frozen</td><td className="py-2 text-gray-800">Congelado (-18°C)</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">ultra_frozen</td><td className="py-2 text-gray-800">Ultra congelado (-80°C)</td></tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-primary-500" /> Trazabilidad de Productos
                </CardTitle>
              </CardHeader>
              <div className="text-sm">
                <table className="w-full">
                  <tbody className="divide-y divide-gray-100">
                    <tr><td className="py-2 font-mono text-xs text-gray-600">none</td><td className="py-2 text-gray-800">Sin trazabilidad (Granel)</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">lot</td><td className="py-2 text-gray-800">Por número de Lote</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">serial</td><td className="py-2 text-gray-800">Por número de Serie (1:1)</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">lot_expiry</td><td className="py-2 text-gray-800">Lote + Fecha Vencimiento</td></tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-primary-500" /> Estrategias de Rotación
                </CardTitle>
              </CardHeader>
              <div className="text-sm">
                <table className="w-full">
                  <tbody className="divide-y divide-gray-100">
                    <tr><td className="py-2 font-mono text-xs text-gray-600">FEFO</td><td className="py-2 text-gray-800">First Expired, First Out</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">FIFO</td><td className="py-2 text-gray-800">First In, First Out</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">LIFO</td><td className="py-2 text-gray-800">Last In, First Out</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">LEFO</td><td className="py-2 text-gray-800">Least Expired, First Out</td></tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-primary-500" /> Tipos de Ubicaciones
                </CardTitle>
              </CardHeader>
              <div className="text-sm">
                <table className="w-full">
                  <tbody className="divide-y divide-gray-100">
                    <tr><td className="py-2 font-mono text-xs text-gray-600">standard</td><td className="py-2 text-gray-800">Ubicación Estándar Picking</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">bulk</td><td className="py-2 text-gray-800">Zona de Bulto/Reserva</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">floor</td><td className="py-2 text-gray-800">Piso (sin rack)</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">mezzanine</td><td className="py-2 text-gray-800">Mezanine</td></tr>
                    <tr><td className="py-2 font-mono text-xs text-gray-600">cold_room</td><td className="py-2 text-gray-800">Cuarto Frío</td></tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card className="md:col-span-2 lg:col-span-1">
              <CardHeader>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-primary-500" /> Razones de Ajuste de Inventario
                </CardTitle>
              </CardHeader>
              <div className="text-sm space-y-1">
                {reasonCodes.map(rc => (
                  <div key={rc.code}
                    className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 group">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-xs text-gray-600 shrink-0">{rc.code}</span>
                      <span className="text-gray-700 truncate">{rc.label}</span>
                    </div>
                    {rc.isSystem ? (
                      <span title="Código de sistema — no eliminable">
                        <Lock className="h-3 w-3 text-gray-300 shrink-0" />
                      </span>
                    ) : (
                      <button
                        onClick={() => {
                          removeCode(rc.code)
                          toast.success(`Código "${rc.code}" eliminado`)
                        }}
                        title="Eliminar código personalizado"
                        className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition-all shrink-0"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {/* Formulario inline para agregar */}
              <div className="mt-4 pt-4 border-t border-gray-100 space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Agregar nuevo código</p>
                <div className="flex gap-2">
                  <input
                    value={newCode}
                    onChange={e => setNewCode(e.target.value)}
                    placeholder="CÓDIGO"
                    className="h-8 w-28 rounded-lg border border-gray-300 bg-white px-2 text-xs font-mono uppercase placeholder:normal-case placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <input
                    value={newLabel}
                    onChange={e => setNewLabel(e.target.value)}
                    placeholder="Descripción (opcional)"
                    className="h-8 flex-1 rounded-lg border border-gray-300 bg-white px-2 text-xs placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    onKeyDown={e => e.key === 'Enter' && newCode.trim() && handleAddCode()}
                  />
                  <Button
                    size="sm"
                    disabled={!newCode.trim() || alreadyExists}
                    onClick={handleAddCode}
                    className="h-8 px-2"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
                {alreadyExists && (
                  <p className="text-xs text-amber-600">Ese código ya existe en la lista.</p>
                )}
              </div>
            </Card>

          </div>
        )}

      </div>
    </div>
  )
}
