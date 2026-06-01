import { Bell, Search, RefreshCw } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

interface NavbarProps {
  title?: string
}

export function Navbar({ title }: NavbarProps) {
  const { user } = useAuthStore()

  return (
    <header className="h-16 bg-white border-b border-gray-100 flex items-center gap-4 px-6 sticky top-0 z-20">
      {/* Search */}
      <div className="flex-1 flex items-center gap-2 max-w-md">
        <Search className="h-4 w-4 text-gray-400 flex-shrink-0" />
        <input
          type="text"
          placeholder="Buscar productos, OCs, SOs..."
          className="w-full text-sm bg-transparent outline-none placeholder:text-gray-400 text-gray-700"
        />
      </div>

      {/* Page title (mobile) */}
      {title && (
        <h1 className="text-sm font-semibold text-gray-800 hidden lg:block">{title}</h1>
      )}

      <div className="ml-auto flex items-center gap-2">
        {/* Refresh */}
        <button className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
          <RefreshCw className="h-4 w-4" />
        </button>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
          <Bell className="h-4 w-4" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />
        </button>

        {/* Avatar */}
        <div className="flex items-center gap-2 pl-2 border-l border-gray-100">
          <div className="w-7 h-7 rounded-full bg-primary-600 flex items-center justify-center text-xs font-bold text-white">
            {user?.full_name?.charAt(0) ?? 'U'}
          </div>
          <span className="text-sm font-medium text-gray-700 hidden sm:block">
            {user?.full_name?.split(' ')[0]}
          </span>
        </div>
      </div>
    </header>
  )
}
