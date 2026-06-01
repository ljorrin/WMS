import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { User as UserIcon, KeyRound, Warehouse as WarehouseIcon, ShieldCheck } from 'lucide-react'
import { authApi, warehouseApi } from '@/api/endpoints'
import { useAuthStore } from '@/store/authStore'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import toast from 'react-hot-toast'

export function SettingsPage() {
  const { user } = useAuthStore()

  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')

  const { data: warehouses, isLoading: whLoading } = useQuery({
    queryKey: ['warehouses', 'settings'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  const changePwdMut = useMutation({
    mutationFn: () => authApi.changePassword(currentPwd, newPwd),
    onSuccess: () => {
      toast.success('Contraseña actualizada')
      setCurrentPwd(''); setNewPwd(''); setConfirmPwd('')
    },
    onError: () => toast.error('No se pudo actualizar la contraseña'),
  })

  const pwdValid = currentPwd.length >= 1 && newPwd.length >= 8 && newPwd === confirmPwd

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Configuración</h1>
        <p className="text-sm text-gray-500 mt-0.5">Perfil, seguridad y bodegas del tenant</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Perfil */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserIcon className="h-4 w-4" /> Perfil
            </CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between py-1.5 border-b border-gray-50">
              <span className="text-gray-500">Nombre</span>
              <span className="font-medium text-gray-900">{user?.full_name ?? '—'}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-gray-50">
              <span className="text-gray-500">Usuario</span>
              <span className="font-mono text-gray-700">{user?.username ?? '—'}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-gray-50">
              <span className="text-gray-500">Email</span>
              <span className="text-gray-700">{user?.email ?? '—'}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-gray-50">
              <span className="text-gray-500">Estado</span>
              <Badge status={user?.is_active ? 'active' : 'inactive'}
                label={user?.is_active ? 'Activo' : 'Inactivo'} />
            </div>
            <div className="py-1.5">
              <span className="text-gray-500 flex items-center gap-1 mb-1.5">
                <ShieldCheck className="h-3.5 w-3.5" /> Roles
              </span>
              <div className="flex flex-wrap gap-1">
                {user?.roles?.length
                  ? user.roles.map(r => <Badge key={r} status="confirmed" label={r} />)
                  : <span className="text-gray-400">Sin roles</span>}
              </div>
            </div>
          </div>
        </Card>

        {/* Cambio de contraseña */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" /> Cambiar contraseña
            </CardTitle>
          </CardHeader>
          <div className="space-y-3">
            <Input label="Contraseña actual" type="password" value={currentPwd}
              onChange={e => setCurrentPwd(e.target.value)} placeholder="••••••••" />
            <Input label="Nueva contraseña" type="password" value={newPwd}
              onChange={e => setNewPwd(e.target.value)} placeholder="Mínimo 8 caracteres"
              error={newPwd.length > 0 && newPwd.length < 8 ? 'Mínimo 8 caracteres' : undefined} />
            <Input label="Confirmar nueva contraseña" type="password" value={confirmPwd}
              onChange={e => setConfirmPwd(e.target.value)} placeholder="Repite la contraseña"
              error={confirmPwd.length > 0 && confirmPwd !== newPwd ? 'No coincide' : undefined} />
            <Button size="sm" disabled={!pwdValid} loading={changePwdMut.isPending}
              onClick={() => changePwdMut.mutate()}>Actualizar contraseña</Button>
          </div>
        </Card>
      </div>

      {/* Bodegas */}
      <Card padding={false}>
        <div className="px-5 py-4 border-b border-gray-100">
          <CardTitle className="flex items-center gap-2">
            <WarehouseIcon className="h-4 w-4" /> Bodegas ({warehouses?.total ?? 0})
          </CardTitle>
        </div>
        <Table>
          <Thead>
            <Tr>
              <Th>Código</Th>
              <Th>Nombre</Th>
              <Th>Tipo</Th>
              <Th>Ciudad</Th>
              <Th>Cadena de frío</Th>
              <Th>Estrategia picking</Th>
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
              <EmptyRow cols={7} message="No hay bodegas configuradas" />
            ) : (
              warehouses.items.map(w => (
                <Tr key={w.id}>
                  <Td><span className="font-mono font-medium text-primary-700">{w.code}</span></Td>
                  <Td className="font-medium text-gray-900">{w.name}</Td>
                  <Td className="text-xs text-gray-500 capitalize">{w.type}</Td>
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
    </div>
  )
}
