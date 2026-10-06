import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, MapPin, Package, Send, XCircle } from 'lucide-react'
import { integrationsApi } from '@/api/endpoints'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { fmt } from '@/utils/format'
import type { TmsOrderPreview, TmsSendResult } from '@/types'
import toast from 'react-hot-toast'

/** Qué enviar: envíos concretos o todos los pendientes aún no enviados. */
export type TmsSendTarget = { ids: string[] } | { all: true }

interface Props {
  target: TmsSendTarget | null
  onClose: () => void
}

const CARGA: Record<string, string> = {
  consumo_masivo: 'Consumo masivo', refrigerada: 'Refrigerada', farmaceutica: 'Farmacéutica',
  peligrosa: 'Peligrosa', fragil: 'Frágil', repuestos: 'Repuestos',
}
const PRIORIDAD: Record<string, string> = {
  normal: 'Normal', express: 'Express', same_day: 'Mismo día', programada: 'Programada',
}
const FALTANTE: Record<string, string> = {
  'destino.lat/lon': 'coordenadas del destino',
  'destino.direccion': 'dirección de entrega',
  peso_kg: 'peso',
}
const RESULTADO: Record<TmsSendResult['resultado'], { label: string; cls: string }> = {
  creada: { label: 'Creada en el TMS', cls: 'text-green-700' },
  ya_existia: { label: 'Ya estaba en el TMS', cls: 'text-green-700' },
  incompleta: { label: 'No enviada: faltan datos', cls: 'text-amber-600' },
  error: { label: 'Error', cls: 'text-red-600' },
}

const hora = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('es-PA', { hour: '2-digit', minute: '2-digit' }) : ''

export function TmsSendModal({ target, onClose }: Props) {
  const qc = useQueryClient()
  const open = target !== null
  const [includeIncomplete, setIncludeIncomplete] = useState(false)
  const [results, setResults] = useState<TmsSendResult[] | null>(null)

  useEffect(() => {
    if (open) { setIncludeIncomplete(false); setResults(null) }
  }, [open])

  const body = target && ('all' in target ? { all_pending: true } : { shipment_ids: target.ids })
  const { data, isLoading, isError } = useQuery({
    queryKey: ['tms-preview', body],
    queryFn: () => integrationsApi.previewTms(body!),
    enabled: open,
    staleTime: 0,
  })

  const items = data?.items ?? []
  const complete = useMemo(() => items.filter(o => !o.faltantes.length), [items])
  const incomplete = useMemo(() => items.filter(o => o.faltantes.length), [items])
  const toSend = includeIncomplete ? items : complete

  const sendMut = useMutation({
    mutationFn: () => integrationsApi.sendToTms({
      shipment_ids: toSend.map(o => o.referencia_externa),
      force: includeIncomplete,
    }),
    onSuccess: res => {
      qc.invalidateQueries({ queryKey: ['shipments'] })
      setResults(res.resultados)
      const ok = res.resultados.filter(r => r.resultado === 'creada' || r.resultado === 'ya_existia').length
      if (ok) toast.success(`${ok} envío(s) en el TMS`)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'No se pudo enviar al TMS'),
  })

  const close = () => { if (!sendMut.isPending) onClose() }

  // ── Paso 2: resultado ──────────────────────────────────────────────────
  if (results) {
    const byId = new Map(items.map(o => [o.referencia_externa, o]))
    return (
      <Modal open={open} onClose={close} size="lg" title="Resultado del envío al TMS"
        description="El TMS planificará las rutas; el despacho y la entrega se reflejarán aquí automáticamente."
        footer={<Button size="sm" onClick={onClose}>Cerrar</Button>}>
        <ul className="divide-y divide-gray-100">
          {results.map(r => {
            const st = RESULTADO[r.resultado]
            const ok = r.resultado === 'creada' || r.resultado === 'ya_existia'
            return (
              <li key={r.shipment_id} className="flex items-start gap-3 py-2.5">
                {ok ? <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600 shrink-0" />
                  : <XCircle className="h-4 w-4 mt-0.5 text-red-500 shrink-0" />}
                <div className="min-w-0 flex-1">
                  <p className="text-sm">
                    <span className="font-mono font-medium text-primary-700">{r.numero}</span>
                    <span className="text-gray-500"> · {byId.get(r.shipment_id)?.cliente.nombre}</span>
                  </p>
                  <p className={`text-xs ${st.cls}`}>
                    {st.label}{r.error && !ok ? ` — ${r.error}` : ''}
                    {r.tms_order_id && <span className="text-gray-400"> · Orden TMS {r.tms_order_id.slice(0, 8)}</span>}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>
      </Modal>
    )
  }

  // ── Paso 1: confirmación ───────────────────────────────────────────────
  return (
    <Modal open={open} onClose={close} size="lg" title="Enviar al TMS"
      description="Revisa los datos con los que llegarán las órdenes al TMS antes de confirmar."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={close} disabled={sendMut.isPending}>Cancelar</Button>
          <Button size="sm" disabled={!toSend.length || isLoading} loading={sendMut.isPending}
            onClick={() => sendMut.mutate()}>
            <Send className="h-4 w-4" />
            {toSend.length === 1 ? 'Enviar 1 orden' : `Enviar ${toSend.length} órdenes`}
          </Button>
        </>
      }>
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-16 rounded-lg bg-gray-100 animate-pulse" />)}
        </div>
      ) : isError ? (
        <p className="text-sm text-red-600">No se pudo preparar la vista previa.</p>
      ) : !items.length ? (
        <p className="text-sm text-gray-500">No hay envíos pendientes por enviar al TMS.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-green-50 px-2.5 py-1 font-medium text-green-700">
              {complete.length} lista(s) para rutear
            </span>
            {incomplete.length > 0 && (
              <span className="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-700">
                {incomplete.length} con datos faltantes
              </span>
            )}
          </div>

          <ul className="space-y-2">
            {items.map(o => <OrderRow key={o.referencia_externa} o={o}
              excluded={!!o.faltantes.length && !includeIncomplete} />)}
          </ul>

          {incomplete.length > 0 && (
            <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-sm text-amber-900 cursor-pointer">
              <input type="checkbox" className="mt-0.5" checked={includeIncomplete}
                onChange={e => setIncludeIncomplete(e.target.checked)} />
              <span>
                Enviar también las órdenes con datos faltantes. El TMS intentará geocodificar la dirección;
                si no lo logra, habrá que ubicarlas a mano en el TMS antes de planificar.
                <span className="block text-xs text-amber-700 mt-0.5">
                  Lo recomendable es completar la dirección y las coordenadas en la SO o en la ficha del cliente.
                </span>
              </span>
            </label>
          )}
        </div>
      )}
    </Modal>
  )
}

function OrderRow({ o, excluded }: { o: TmsOrderPreview; excluded: boolean }) {
  const d = o.destino
  const geo = d.lat != null && d.lon != null
  const ventana = o.ventana_desde
    ? `${fmt.date(o.ventana_desde)} ${hora(o.ventana_desde)}–${hora(o.ventana_hasta)}`
    : o.fecha_compromiso ? fmt.date(o.fecha_compromiso) : 'Sin fecha'
  return (
    <li className={`rounded-lg border p-3 ${o.faltantes.length ? 'border-amber-200 bg-amber-50/40' : 'border-gray-100'}
      ${excluded ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm">
          <span className="font-mono font-semibold text-primary-700">{o.numero}</span>
          <span className="text-gray-700"> · {o.cliente.nombre}</span>
        </p>
        <div className="flex gap-1.5 text-[11px] font-medium">
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700">{CARGA[o.tipo_mercancia] ?? o.tipo_mercancia}</span>
          <span className={`rounded px-1.5 py-0.5 ${o.prioridad === 'normal' ? 'bg-gray-100 text-gray-700' : 'bg-primary-50 text-primary-700'}`}>
            {PRIORIDAD[o.prioridad] ?? o.prioridad}
          </span>
          {o.enviado_tms && <span className="rounded bg-green-50 px-1.5 py-0.5 text-green-700">Ya enviada</span>}
        </div>
      </div>
      <div className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
        <p className="flex items-start gap-1">
          <MapPin className={`h-3.5 w-3.5 mt-px shrink-0 ${geo ? 'text-green-600' : 'text-amber-600'}`} />
          <span>
            {d.direccion ?? <em className="text-amber-700">Sin dirección</em>}{d.ciudad ? `, ${d.ciudad}` : ''}
            <span className="block text-gray-400">
              {geo ? `${d.lat?.toFixed(5)}, ${d.lon?.toFixed(5)}` : 'Sin coordenadas'}
              {d.horario_desde && ` · recibe ${d.horario_desde}–${d.horario_hasta}`}
            </span>
          </span>
        </p>
        <p className="flex items-start gap-1">
          <Package className="h-3.5 w-3.5 mt-px shrink-0 text-gray-400" />
          <span>
            {o.peso_kg.toLocaleString('es-PA')} kg · {o.bultos ?? '—'} bultos
            {o.volumen_m3 ? ` · ${o.volumen_m3} m³` : ''} · {o.lineas.length} línea(s)
            <span className="block text-gray-400">Entrega: {ventana}</span>
          </span>
        </p>
      </div>
      {o.faltantes.length > 0 && (
        <p className="mt-1.5 flex items-center gap-1 text-xs font-medium text-amber-700">
          <AlertTriangle className="h-3.5 w-3.5" />
          Falta: {o.faltantes.map(f => FALTANTE[f] ?? f).join(', ')}
        </p>
      )}
      {o.advertencias.length > 0 && (
        <p className="mt-1 text-[11px] text-gray-500">{o.advertencias.join(' · ')}</p>
      )}
    </li>
  )
}
