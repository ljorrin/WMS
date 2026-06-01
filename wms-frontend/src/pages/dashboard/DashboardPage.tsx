import { useQuery } from '@tanstack/react-query'
import {
  TruckIcon, SendHorizonal, Boxes, AlertTriangle,
  PackageCheck, Clock, BarChart3, Ship,
} from 'lucide-react'
import { KpiCard } from '@/components/ui/KpiCard'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { inboundApi, outboundApi } from '@/api/endpoints'
import { fmt } from '@/utils/format'
import { format, parseISO } from 'date-fns'
import { es } from 'date-fns/locale'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Legend,
} from 'recharts'

// Etiqueta corta de día (Lun, Mar…) capitalizada a partir de una fecha ISO
const dayLabel = (iso: string) => {
  const l = format(parseISO(iso), 'EEE', { locale: es })
  return l.charAt(0).toUpperCase() + l.slice(1)
}

export function DashboardPage() {
  const { data: inbound, isLoading: inboundLoading } = useQuery({
    queryKey: ['inbound-dashboard'],
    queryFn: () => inboundApi.getDashboard(),
    refetchInterval: 60_000,
  })

  const { data: outbound, isLoading: outboundLoading } = useQuery({
    queryKey: ['outbound-dashboard'],
    queryFn: () => outboundApi.getDashboard(),
    refetchInterval: 60_000,
  })

  const { data: inboundThroughput } = useQuery({
    queryKey: ['inbound-throughput'],
    queryFn: () => inboundApi.getThroughput(7),
    refetchInterval: 60_000,
  })

  const { data: outboundThroughput } = useQuery({
    queryKey: ['outbound-throughput'],
    queryFn: () => outboundApi.getThroughput(7),
    refetchInterval: 60_000,
  })

  const receiptData = (inboundThroughput?.series ?? []).map(p => ({
    day: dayLabel(p.day), GRNs: p.grns, Putaway: p.putaway_completed,
  }))

  const pickingData = (outboundThroughput?.series ?? []).map(p => ({
    day: dayLabel(p.day), Picks: p.picks, Shorts: p.shorts,
  }))

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">Vista general del almacén en tiempo real</p>
      </div>

      {/* ── INBOUND KPIs ──────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3 flex items-center gap-2">
          <TruckIcon className="h-4 w-4" /> Inbound
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="OCs Abiertas"
            value={inbound?.pos_open ?? '—'}
            icon={Boxes}
            loading={inboundLoading}
          />
          <KpiCard
            title="OCs Vencidas"
            value={inbound?.pos_overdue ?? '—'}
            icon={AlertTriangle}
            alert={(inbound?.pos_overdue ?? 0) > 0}
            loading={inboundLoading}
          />
          <KpiCard
            title="GRNs Hoy"
            value={inbound?.grns_today ?? '—'}
            icon={TruckIcon}
            loading={inboundLoading}
          />
          <KpiCard
            title="Putaway Pendiente"
            value={inbound?.putaway_tasks_open ?? '—'}
            subtitle={inbound?.avg_putaway_cycle_time_seconds
              ? `Tiempo promedio: ${fmt.seconds(inbound.avg_putaway_cycle_time_seconds)}`
              : undefined}
            icon={PackageCheck}
            loading={inboundLoading}
          />
        </div>
      </section>

      {/* ── OUTBOUND KPIs ─────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3 flex items-center gap-2">
          <SendHorizonal className="h-4 w-4" /> Outbound
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Órdenes Abiertas"
            value={outbound?.orders_open ?? '—'}
            icon={BarChart3}
            loading={outboundLoading}
          />
          <KpiCard
            title="Picks Hoy"
            value={outbound?.picks_today ?? '—'}
            subtitle={outbound?.avg_pick_cycle_time_seconds
              ? `Tiempo promedio: ${fmt.seconds(outbound.avg_pick_cycle_time_seconds)}`
              : undefined}
            icon={Boxes}
            loading={outboundLoading}
          />
          <KpiCard
            title="Envíos Hoy"
            value={outbound?.shipments_today ?? '—'}
            icon={Ship}
            loading={outboundLoading}
          />
          <KpiCard
            title="Órdenes Vencidas"
            value={outbound?.orders_overdue ?? '—'}
            icon={AlertTriangle}
            alert={(outbound?.orders_overdue ?? 0) > 0}
            loading={outboundLoading}
          />
        </div>
      </section>

      {/* ── CHARTS ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Recepciones esta semana</CardTitle>
            <Clock className="h-4 w-4 text-gray-400" />
          </CardHeader>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={receiptData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="grn" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Area type="monotone" dataKey="GRNs" stroke="#3b82f6" fill="url(#grn)" strokeWidth={2} />
              <Area type="monotone" dataKey="Putaway" stroke="#8b5cf6" fill="none" strokeWidth={2} strokeDasharray="4 2" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Picking esta semana</CardTitle>
            <Clock className="h-4 w-4 text-gray-400" />
          </CardHeader>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={pickingData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Picks" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Shorts" fill="#f97316" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ── ALERTS ROW ────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Estado Inbound</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">Pendientes QC</span>
              <Badge status={inbound?.grns_pending_qc ? 'pending' : 'active'}
                     label={String(inbound?.grns_pending_qc ?? 0)} />
            </div>
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">Tasa de defectos</span>
              <span className="font-medium">{fmt.pct(inbound?.avg_defect_rate_pct)}</span>
            </div>
            <div className="flex justify-between items-center py-1.5">
              <span className="text-gray-600">RTV pendientes</span>
              <Badge status={inbound?.rtv_pending ? 'pending' : 'active'}
                     label={String(inbound?.rtv_pending ?? 0)} />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Estado Outbound</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">Por pickear</span>
              <span className="font-medium">{outbound?.orders_pending_pick ?? '—'}</span>
            </div>
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">Por empacar</span>
              <span className="font-medium">{outbound?.orders_pending_pack ?? '—'}</span>
            </div>
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">Por despachar</span>
              <span className="font-medium">{outbound?.orders_pending_ship ?? '—'}</span>
            </div>
            <div className="flex justify-between items-center py-1.5">
              <span className="text-gray-600">En tránsito</span>
              <Badge status="shipped" label={String(outbound?.shipments_in_transit ?? 0)} />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>KPIs Clave</CardTitle>
          </CardHeader>
          <div className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">Short Pick Rate</span>
              <span className={`font-medium ${(outbound?.short_pick_rate_pct ?? 0) > 5 ? 'text-red-600' : 'text-green-600'}`}>
                {fmt.pct(outbound?.short_pick_rate_pct)}
              </span>
            </div>
            <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
              <span className="text-gray-600">On-Time Delivery</span>
              <span className="font-medium">{fmt.pct(outbound?.on_time_delivery_pct)}</span>
            </div>
            <div className="flex justify-between items-center py-1.5">
              <span className="text-gray-600">Fill Rate</span>
              <span className="font-medium">{fmt.pct(outbound?.order_fill_rate_pct)}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
