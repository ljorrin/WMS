import { format, formatDistanceToNow, parseISO } from 'date-fns'
import { es } from 'date-fns/locale'

export const fmt = {
  date: (d?: string | null) =>
    d ? format(parseISO(d), 'dd/MM/yyyy', { locale: es }) : '—',

  datetime: (d?: string | null) =>
    d ? format(parseISO(d), 'dd/MM/yyyy HH:mm', { locale: es }) : '—',

  relative: (d?: string | null) =>
    d ? formatDistanceToNow(parseISO(d), { addSuffix: true, locale: es }) : '—',

  currency: (n?: number | null, currency = 'USD') =>
    n != null
      ? new Intl.NumberFormat('es-PA', { style: 'currency', currency }).format(n)
      : '—',

  number: (n?: number | null, decimals = 2) =>
    n != null ? n.toLocaleString('es-PA', { maximumFractionDigits: decimals }) : '—',

  pct: (n?: number | null) =>
    n != null ? `${n.toFixed(1)}%` : '—',

  seconds: (s?: number | null) => {
    if (s == null) return '—'
    const m = Math.floor(s / 60)
    const sec = s % 60
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
  },
}

export const STATUS_COLORS: Record<string, string> = {
  // Generic
  active:    'bg-green-100 text-green-700',
  inactive:  'bg-gray-100 text-gray-600',
  // PO / GRN
  draft:             'bg-gray-100 text-gray-600',
  confirmed:         'bg-blue-100 text-blue-700',
  partially_received:'bg-amber-100 text-amber-700',
  closed:            'bg-green-100 text-green-700',
  cancelled:         'bg-red-100 text-red-700',
  in_progress:       'bg-blue-100 text-blue-700',
  putaway_in_progress:'bg-purple-100 text-purple-700',
  completed:         'bg-green-100 text-green-700',
  rejected:          'bg-red-100 text-red-700',
  // QC
  pending:           'bg-amber-100 text-amber-700',
  approved:          'bg-green-100 text-green-700',
  // SO
  allocated:         'bg-indigo-100 text-indigo-700',
  picking:           'bg-cyan-100 text-cyan-700',
  packed:            'bg-purple-100 text-purple-700',
  shipped:           'bg-teal-100 text-teal-700',
  delivered:         'bg-green-100 text-green-700',
  // Wave
  open:              'bg-gray-100 text-gray-600',
  released:          'bg-blue-100 text-blue-700',
  // Picking
  short_picked:      'bg-orange-100 text-orange-700',
  // Inventory batch / stock
  quarantine:        'bg-amber-100 text-amber-700',
  damaged:           'bg-red-100 text-red-700',
  expired:           'bg-red-100 text-red-700',
  // Adjustments
  pending_approval:  'bg-amber-100 text-amber-700',
  applied:           'bg-green-100 text-green-700',
  // QC
  passed:            'bg-green-100 text-green-700',
  partial:           'bg-orange-100 text-orange-700',
  conditionally_released: 'bg-yellow-100 text-yellow-700',
  // Shipment / RMA
  ready:             'bg-blue-100 text-blue-700',
  in_transit:        'bg-teal-100 text-teal-700',
  failed:            'bg-red-100 text-red-700',
  returned:          'bg-orange-100 text-orange-700',
  requested:         'bg-gray-100 text-gray-600',
  received:          'bg-indigo-100 text-indigo-700',
  inspected:         'bg-purple-100 text-purple-700',
}
