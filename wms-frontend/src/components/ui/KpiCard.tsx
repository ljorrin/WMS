import { LucideIcon } from 'lucide-react'
import { cn } from '@/utils/cn'

interface KpiCardProps {
  title: string
  value: string | number
  subtitle?: string
  icon: LucideIcon
  iconColor?: string
  trend?: { value: number; label: string; positive?: boolean }
  alert?: boolean
  loading?: boolean
}

export function KpiCard({
  title, value, subtitle, icon: Icon,
  iconColor = 'text-primary-600',
  trend, alert = false, loading = false,
}: KpiCardProps) {
  return (
    <div className={cn(
      'rounded-xl bg-white border shadow-card p-5 flex flex-col gap-3 transition-shadow hover:shadow-card-hover',
      alert ? 'border-red-200 bg-red-50' : 'border-gray-100'
    )}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
          {loading ? (
            <div className="mt-1 h-8 w-24 rounded bg-gray-200 animate-pulse" />
          ) : (
            <p className={cn(
              'mt-1 text-3xl font-bold',
              alert ? 'text-red-700' : 'text-gray-900'
            )}>
              {value}
            </p>
          )}
          {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
        </div>
        <div className={cn(
          'p-2.5 rounded-xl',
          alert ? 'bg-red-100' : 'bg-primary-50'
        )}>
          <Icon className={cn('h-5 w-5', alert ? 'text-red-600' : iconColor)} />
        </div>
      </div>

      {trend && (
        <div className="flex items-center gap-1 text-xs">
          <span className={cn(
            'font-medium',
            trend.positive ? 'text-green-600' : 'text-red-500'
          )}>
            {trend.positive ? '▲' : '▼'} {Math.abs(trend.value)}%
          </span>
          <span className="text-gray-400">{trend.label}</span>
        </div>
      )}
    </div>
  )
}
