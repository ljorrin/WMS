import { cn } from '@/utils/cn'
import { STATUS_COLORS } from '@/utils/format'

interface BadgeProps {
  status: string
  label?: string
  className?: string
}

export function Badge({ status, label, className }: BadgeProps) {
  const colorClass = STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={cn(
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
      colorClass, className
    )}>
      {label ?? status.replace(/_/g, ' ')}
    </span>
  )
}
