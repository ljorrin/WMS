import { Button } from './Button'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  if (total <= pageSize) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
      <p className="text-xs text-gray-500">
        Mostrando {from}–{to} de {total}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={page === 1}
          onClick={() => onPageChange(page - 1)}>Anterior</Button>
        <Button variant="secondary" size="sm"
          disabled={page * pageSize >= total}
          onClick={() => onPageChange(page + 1)}>Siguiente</Button>
      </div>
    </div>
  )
}
