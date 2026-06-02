import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Check, Loader2 } from 'lucide-react'
import { cn } from '@/utils/cn'

interface ComboboxProps<T> {
  label?: string
  placeholder?: string
  value?: string
  displayLabel?: string
  queryKey: string
  /** Devuelve el listado filtrado por el texto de búsqueda. */
  fetcher: (search: string) => Promise<{ items: T[] }>
  getKey: (item: T) => string
  getLabel: (item: T) => string
  onSelect: (item: T) => void
  disabled?: boolean
  error?: string
}

export function Combobox<T>({
  label, placeholder, value, displayLabel, queryKey,
  fetcher, getKey, getLabel, onSelect, disabled, error,
}: ComboboxProps<T>) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const { data, isFetching } = useQuery({
    queryKey: [queryKey, 'combobox', search],
    queryFn: () => fetcher(search),
    enabled: open,
    placeholderData: prev => prev,
  })

  const items = data?.items ?? []

  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-sm font-medium text-gray-700">{label}</label>}
      <div className="relative">
        <div className="relative">
          <input
            disabled={disabled}
            value={open ? search : (displayLabel ?? '')}
            placeholder={displayLabel || placeholder}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onChange={e => setSearch(e.target.value)}
            className={cn(
              'h-9 w-full rounded-lg border border-gray-300 bg-white px-3 pr-8 text-sm',
              'placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
              'disabled:opacity-50 disabled:bg-gray-50',
              error && 'border-red-400 focus:ring-red-500'
            )}
          />
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400">
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronDown className="h-4 w-4" />}
          </span>
        </div>

        {open && (
          <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
            {items.length === 0 ? (
              <p className="px-3 py-2 text-xs text-gray-400">
                {isFetching ? 'Buscando…' : 'Sin resultados'}
              </p>
            ) : (
              items.map(item => {
                const key = getKey(item)
                const selected = key === value
                return (
                  <button
                    key={key}
                    type="button"
                    onMouseDown={e => { e.preventDefault(); onSelect(item); setOpen(false); setSearch('') }}
                    className={cn(
                      'flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors',
                      selected ? 'bg-primary-50 text-primary-800' : 'text-gray-700 hover:bg-gray-50'
                    )}
                  >
                    <span className="truncate">{getLabel(item)}</span>
                    {selected && <Check className="h-4 w-4 shrink-0 text-primary-600" />}
                  </button>
                )
              })
            )}
          </div>
        )}
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}
