import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Package, TruckIcon, SendHorizonal,
  BarChart3, Settings, LogOut, ChevronDown, Warehouse,
  ClipboardList, Boxes, Route, PackageCheck, Ship,
  RefreshCw, AlertCircle, ScanLine,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { useAuthStore } from '@/store/authStore'
import { useState } from 'react'

interface NavItem {
  label: string
  icon: React.ElementType
  href?: string
  children?: NavItem[]
}

const navItems: NavItem[] = [
  { label: 'Dashboard', icon: LayoutDashboard, href: '/' },
  {
    label: 'Inventario', icon: Boxes, children: [
      { label: 'Stock', icon: Package, href: '/inventory/stock' },
      { label: 'Movimientos', icon: BarChart3, href: '/inventory/movements' },
      { label: 'Ajustes', icon: ClipboardList, href: '/inventory/adjustments' },
      { label: 'Por Vencer', icon: AlertCircle, href: '/inventory/expiry' },
    ],
  },
  {
    label: 'Inbound', icon: TruckIcon, children: [
      { label: 'Órdenes de Compra', icon: ClipboardList, href: '/inbound/pos' },
      { label: 'Recepciones (GRN)', icon: Warehouse, href: '/inbound/grns' },
      { label: 'Control de Calidad', icon: ScanLine, href: '/inbound/quality' },
      { label: 'Putaway', icon: Route, href: '/inbound/putaway' },
    ],
  },
  {
    label: 'Outbound', icon: SendHorizonal, children: [
      { label: 'Órdenes de Venta', icon: ClipboardList, href: '/outbound/orders' },
      { label: 'Waves de Picking', icon: Boxes, href: '/outbound/waves' },
      { label: 'Picking', icon: ScanLine, href: '/outbound/picking' },
      { label: 'Empaque', icon: PackageCheck, href: '/outbound/packing' },
      { label: 'Envíos', icon: Ship, href: '/outbound/shipments' },
      { label: 'Devoluciones', icon: RefreshCw, href: '/outbound/returns' },
    ],
  },
  { label: 'Configuración', icon: Settings, href: '/settings' },
]

function NavGroup({ item }: { item: NavItem }) {
  const location = useLocation()
  const isActive = item.children?.some(c => c.href && location.pathname.startsWith(c.href))
  const [open, setOpen] = useState(isActive ?? false)

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
          isActive
            ? 'bg-primary-600/20 text-primary-300'
            : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
        )}
      >
        <item.icon className="h-4 w-4 flex-shrink-0" />
        <span className="flex-1 text-left">{item.label}</span>
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      {open && item.children && (
        <div className="mt-1 ml-3 pl-3 border-l border-white/10 flex flex-col gap-0.5">
          {item.children.map(child => (
            <NavLink
              key={child.href}
              to={child.href!}
              className={({ isActive }) => cn(
                'flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
              )}
            >
              <child.icon className="h-3.5 w-3.5" />
              {child.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

export function Sidebar() {
  const { user, logout } = useAuthStore()

  return (
    <aside className="fixed inset-y-0 left-0 w-60 bg-sidebar flex flex-col z-30">
      {/* Logo */}
      <div className="h-16 flex items-center gap-3 px-5 border-b border-white/10">
        <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center">
          <Warehouse className="h-4 w-4 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-none">WMS</p>
          <p className="text-[10px] text-gray-400 leading-none mt-0.5">Panama</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-1">
        {navItems.map(item =>
          item.children ? (
            <NavGroup key={item.label} item={item} />
          ) : (
            <NavLink
              key={item.href}
              to={item.href!}
              end
              className={({ isActive }) => cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          )
        )}
      </nav>

      {/* User */}
      <div className="border-t border-white/10 p-3">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="w-7 h-7 rounded-full bg-primary-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
            {user?.full_name?.charAt(0) ?? 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-200 truncate">{user?.full_name}</p>
            <p className="text-[10px] text-gray-500 truncate">{user?.email}</p>
          </div>
          <button
            onClick={() => logout()}
            title="Cerrar sesión"
            className="text-gray-500 hover:text-gray-300 transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  )
}
