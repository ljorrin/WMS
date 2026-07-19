import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RadioTower, Rss, AlertTriangle, ScanLine, Tags, Copy, Play, Square, Trash2, Radio, Fingerprint,
} from 'lucide-react'
import { hardwareApi, warehouseApi } from '@/api/endpoints'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { KpiCard } from '@/components/ui/KpiCard'
import { Table, Thead, Tbody, Tr, Th, Td, EmptyRow } from '@/components/ui/Table'
import { Pagination } from '@/components/ui/Pagination'
import { fmt } from '@/utils/format'
import type { RfidTagRead } from '@/types'
import toast from 'react-hot-toast'

const PAGE_SIZE = 20

export function RfidTestPage() {
  const [warehouseId, setWarehouseId] = useState('')

  const { data: warehouses } = useQuery({
    queryKey: ['warehouses'],
    queryFn: () => warehouseApi.list({ page_size: 100 }),
  })

  useEffect(() => {
    if (!warehouseId && warehouses?.items.length) setWarehouseId(warehouses.items[0].id)
  }, [warehouses, warehouseId])

  const { data: readers } = useQuery({
    queryKey: ['rfid-readers', warehouseId],
    queryFn: () => hardwareApi.getReaders(warehouseId || undefined),
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pruebas RFID / Hardware</h1>
          <p className="text-sm text-gray-500 mt-1">
            Simula lecturas de tags, revisa el historial decodificado (GS1 EPC) y genera etiquetas ZPL de prueba.
          </p>
        </div>
        <select value={warehouseId} onChange={e => setWarehouseId(e.target.value)}
          className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-700">
          <option value="">Todas las bodegas</option>
          {warehouses?.items.map(w => <option key={w.id} value={w.id}>{w.code} — {w.name}</option>)}
        </select>
      </div>

      <DashboardKpis warehouseId={warehouseId} />

      <LiveScanCard warehouseId={warehouseId} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SimulateReadCard readers={readers?.items ?? []} />
        <ZplLabelCard />
      </div>

      <TagReadsTable warehouseId={warehouseId} />
    </div>
  )
}

function DashboardKpis({ warehouseId }: { warehouseId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['rfid-dashboard', warehouseId],
    queryFn: () => hardwareApi.getDashboard(warehouseId || undefined),
  })

  const onlineReaders = data?.readers_by_status?.online ?? 0
  const totalReaders = Object.values(data?.readers_by_status ?? {}).reduce((a, b) => a + b, 0)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <KpiCard title="Readers Registrados" value={totalReaders} subtitle={`${onlineReaders} en línea`}
        icon={RadioTower} loading={isLoading} />
      <KpiCard title="Lecturas Hoy" value={data?.reads_today ?? 0}
        subtitle="Total de lecturas, incluye repetidas" icon={Rss} loading={isLoading} />
      <KpiCard title="Códigos Únicos Hoy" value={data?.unique_epcs_today ?? 0}
        subtitle="EPCs distintos, sin contar repeticiones" icon={Fingerprint} loading={isLoading} />
      <KpiCard title="Lecturas sin Procesar" value={data?.unprocessed_reads ?? 0}
        icon={AlertTriangle} loading={isLoading} alert={(data?.unprocessed_reads ?? 0) > 0} />
    </div>
  )
}

const GATEWAY_CONTROLLER_URL = 'http://127.0.0.1:8765'

function LiveScanCard({ warehouseId }: { warehouseId: string }) {
  const qc = useQueryClient()
  const [active, setActive] = useState(false)
  const [results, setResults] = useState<RfidTagRead[]>([])
  const startedAtRef = useRef<string | null>(null)
  const seenIdsRef = useRef<Set<string>>(new Set())

  const { data } = useQuery({
    queryKey: ['rfid-live-scan', warehouseId],
    queryFn: () => hardwareApi.getTagReads({
      page: 1, page_size: 50, ...(warehouseId ? { warehouse_id: warehouseId } : {}),
    }),
    enabled: active,
    refetchInterval: active ? 2000 : false,
  })

  useEffect(() => {
    if (!active || !data) return
    const startedAt = startedAtRef.current
    if (!startedAt) return
    const nuevas = data.items.filter(t => t.read_at >= startedAt && !seenIdsRef.current.has(t.id))
    if (nuevas.length) {
      nuevas.forEach(t => seenIdsRef.current.add(t.id))
      setResults(prev => [...nuevas, ...prev])
    }
  }, [data, active])

  const startMut = useMutation({
    mutationFn: async () => {
      const resp = await fetch(`${GATEWAY_CONTROLLER_URL}/start`, { method: 'POST' })
      if (!resp.ok) throw new Error('El controlador respondió con error')
      // Sesión nueva: el dashboard y el historial arrancan en cero.
      await hardwareApi.clearTagReads(warehouseId || undefined)
    },
    onSuccess: () => {
      toast.success('Gateway iniciado — historial y dashboard reiniciados a cero')
      qc.invalidateQueries({ queryKey: ['rfid-dashboard'] })
      qc.invalidateQueries({ queryKey: ['rfid-tag-reads'] })
      startedAtRef.current = new Date().toISOString()
      seenIdsRef.current = new Set()
      setResults([])
      setActive(true)
    },
    onError: () => {
      toast.error(
        'No se pudo conectar con el controlador local (puerto 8765). ' +
        'Corre "python scripts/rfid_gateway_controller.py" en esta máquina y vuelve a intentar.',
        { duration: 6000 },
      )
    },
  })

  const stopMut = useMutation({
    mutationFn: async () => {
      const resp = await fetch(`${GATEWAY_CONTROLLER_URL}/stop`, { method: 'POST' })
      if (!resp.ok) throw new Error('El controlador respondió con error')
    },
    onSuccess: () => toast.success('Gateway detenido'),
    onError: () => toast.error('No se pudo contactar al controlador local para detener el gateway (¿sigue corriendo?)'),
    onSettled: () => setActive(false),
  })

  const clearResults = () => {
    setResults([])
    seenIdsRef.current = new Set()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Radio className="h-5 w-5 text-gray-400" /> Sesión de Lectura en Vivo
        </CardTitle>
      </CardHeader>
      <div className="space-y-3">
        <p className="text-xs text-gray-500">
          "Iniciar Lectura" arranca el gateway LLRP en la máquina conectada al reader (vía el
          controlador local en <code className="font-mono">localhost:8765</code>) y reinicia el
          historial/dashboard a cero. "Detener Lectura" lo apaga.
        </p>
        <div className="flex items-center gap-2">
          {!active ? (
            <Button size="sm" loading={startMut.isPending} onClick={() => startMut.mutate()}>
              <Play className="h-4 w-4" /> Iniciar Lectura
            </Button>
          ) : (
            <Button size="sm" variant="secondary" loading={stopMut.isPending} onClick={() => stopMut.mutate()}>
              <Square className="h-4 w-4" /> Detener Lectura
            </Button>
          )}
          <Button size="sm" variant="secondary" disabled={!results.length} onClick={clearResults}>
            <Trash2 className="h-4 w-4" /> Limpiar Resultados
          </Button>
          {active && (
            <span className="flex items-center gap-1.5 text-xs text-green-600">
              <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" /> Escuchando…
            </span>
          )}
        </div>

        <div className="rounded-lg border border-gray-100 max-h-72 overflow-y-auto">
          {!results.length ? (
            <p className="text-xs text-gray-400 italic text-center py-6">
              {active ? 'Esperando lecturas…' : 'Sin resultados — presiona "Iniciar Lectura" para comenzar.'}
            </p>
          ) : (
            <Table>
              <Thead>
                <Tr>
                  <Th>Hora</Th><Th>EPC</Th><Th>Esquema</Th><Th>GTIN/SSCC</Th><Th>RSSI</Th>
                </Tr>
              </Thead>
              <Tbody>
                {results.map(t => (
                  <Tr key={t.id}>
                    <Td className="text-xs text-gray-500">{fmt.datetime(t.read_at)}</Td>
                    <Td className="font-mono text-xs">{t.epc_hex}</Td>
                    <Td><span className="font-mono text-xs font-semibold text-primary-700">{t.epc_scheme}</span></Td>
                    <Td className="font-mono text-xs">{t.gtin ?? t.sscc ?? '—'}</Td>
                    <Td className="text-xs text-gray-500">{t.rssi_dbm != null ? `${t.rssi_dbm} dBm` : '—'}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          )}
        </div>
      </div>
    </Card>
  )
}

function SimulateReadCard({ readers }: { readers: { code: string; id: string }[] }) {
  const qc = useQueryClient()
  const [readerCode, setReaderCode] = useState('')
  const [antennaNumber, setAntennaNumber] = useState('1')
  const [epcHex, setEpcHex] = useState('')
  const [rssi, setRssi] = useState('-55')
  const [lastResult, setLastResult] = useState<{ scheme: string; gtin?: string | null; sscc?: string | null; product_id?: string | null } | null>(null)

  useEffect(() => {
    if (!readerCode && readers.length) setReaderCode(readers[0].code)
  }, [readers, readerCode])

  const ingestMut = useMutation({
    mutationFn: () => hardwareApi.ingestTagRead({
      reader_code: readerCode,
      antenna_number: antennaNumber ? Number(antennaNumber) : undefined,
      epc_hex: epcHex.trim().toUpperCase(),
      rssi_dbm: rssi ? Number(rssi) : undefined,
    }),
    onSuccess: (res) => {
      toast.success(`Lectura ingerida: esquema ${res.epc_scheme}`)
      setLastResult({ scheme: res.epc_scheme, gtin: res.gtin, sscc: res.sscc, product_id: res.product_id })
      qc.invalidateQueries({ queryKey: ['rfid-tag-reads'] })
      qc.invalidateQueries({ queryKey: ['rfid-dashboard'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'No se pudo ingerir la lectura'),
  })

  const epcValid = /^[0-9A-Fa-f]{24}$/.test(epcHex.trim())
  const canSubmit = readerCode.trim().length > 0 && epcValid

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <ScanLine className="h-5 w-5 text-gray-400" /> Simular Lectura de Tag
        </CardTitle>
      </CardHeader>
      <div className="space-y-3">
        <p className="text-xs text-gray-500">
          Ingresa un EPC de 24 caracteres hex (96 bits, EPC Gen2 — SGTIN-96 o SSCC-96) para simular
          lo que un reader/gateway LLRP real enviaría a <code className="font-mono">POST /hardware/tag-reads</code>.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Reader</label>
            <select value={readerCode} onChange={e => setReaderCode(e.target.value)}
              className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm">
              <option value="">Seleccionar…</option>
              {readers.map(r => <option key={r.id} value={r.code}>{r.code}</option>)}
            </select>
          </div>
          <Input label="Antena #" type="number" min={1} max={32} value={antennaNumber}
            onChange={e => setAntennaNumber(e.target.value)} />
        </div>
        <Input label="EPC (hex, 24 caracteres)" value={epcHex}
          onChange={e => setEpcHex(e.target.value)} placeholder="30340C29B8AC0140000186A0"
          error={epcHex.length > 0 && !epcValid ? 'Debe ser hex de 24 caracteres (96 bits)' : undefined} />
        <Input label="RSSI (dBm)" type="number" value={rssi} onChange={e => setRssi(e.target.value)} />
        <Button size="sm" disabled={!canSubmit} loading={ingestMut.isPending} onClick={() => ingestMut.mutate()}>
          Enviar lectura simulada
        </Button>
        {lastResult && (
          <div className="mt-2 rounded-lg border border-gray-100 bg-gray-50 p-3 text-xs space-y-1">
            <p><span className="text-gray-500">Esquema:</span> <span className="font-mono font-semibold">{lastResult.scheme}</span></p>
            {lastResult.gtin && <p><span className="text-gray-500">GTIN:</span> <span className="font-mono">{lastResult.gtin}</span></p>}
            {lastResult.sscc && <p><span className="text-gray-500">SSCC:</span> <span className="font-mono">{lastResult.sscc}</span></p>}
            <p><span className="text-gray-500">Producto resuelto:</span> {lastResult.product_id ? <span className="font-mono">{lastResult.product_id.slice(0, 8)}…</span> : <span className="text-gray-400">Sin coincidencia</span>}</p>
          </div>
        )}
      </div>
    </Card>
  )
}

function ZplLabelCard() {
  const [sscc, setSscc] = useState('')
  const [companyPrefix, setCompanyPrefix] = useState('')
  const [description, setDescription] = useState('')
  const [encodeRfid, setEncodeRfid] = useState(false)
  const [result, setResult] = useState<{ zpl: string; epc_hex?: string | null; epc_uri?: string | null } | null>(null)

  const genMut = useMutation({
    mutationFn: () => hardwareApi.generateZplSscc({
      sscc: sscc.trim(), company_prefix: companyPrefix.trim(),
      description: description.trim() || undefined, encode_rfid: encodeRfid,
    }),
    onSuccess: (res) => { setResult(res); toast.success('ZPL generado') },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'No se pudo generar el ZPL'),
  })

  const canSubmit = /^\d{18}$/.test(sscc.trim()) && companyPrefix.trim().length >= 6

  const copyZpl = () => {
    if (!result) return
    navigator.clipboard.writeText(result.zpl)
    toast.success('ZPL copiado al portapapeles')
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Tags className="h-5 w-5 text-gray-400" /> Generar Etiqueta ZPL (Pallet/SSCC)
        </CardTitle>
      </CardHeader>
      <div className="space-y-3">
        <Input label="SSCC (18 dígitos)" value={sscc} onChange={e => setSscc(e.target.value)}
          placeholder="106141411234567890" />
        <Input label="Company Prefix (6-12 dígitos)" value={companyPrefix}
          onChange={e => setCompanyPrefix(e.target.value)} placeholder="0614141" />
        <Input label="Descripción (opcional)" value={description} onChange={e => setDescription(e.target.value)}
          placeholder="Nombre legible en la etiqueta" />
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" className="rounded" checked={encodeRfid}
            onChange={e => setEncodeRfid(e.target.checked)} />
          Codificar EPC en el inlay RFID (comando <code className="font-mono">^RFW</code>)
        </label>
        <Button size="sm" disabled={!canSubmit} loading={genMut.isPending} onClick={() => genMut.mutate()}>
          Generar ZPL
        </Button>

        {result && (
          <div className="mt-2 space-y-2">
            {result.epc_hex && (
              <p className="text-xs text-gray-500">
                EPC codificado: <span className="font-mono">{result.epc_hex}</span>
              </p>
            )}
            <div className="relative">
              <pre className="text-[11px] font-mono bg-gray-900 text-gray-100 rounded-lg p-3 max-h-56 overflow-auto whitespace-pre-wrap">{result.zpl}</pre>
              <button onClick={copyZpl} title="Copiar ZPL"
                className="absolute top-2 right-2 text-gray-300 hover:text-white transition-colors">
                <Copy className="h-4 w-4" />
              </button>
            </div>
            <p className="text-xs text-gray-400">
              Envía este código a una impresora Zebra (puerto 9100/USB) o a un emulador ZPL para verlo renderizado.
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}

function TagReadsTable({ warehouseId }: { warehouseId: string }) {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['rfid-tag-reads', warehouseId, page],
    queryFn: () => hardwareApi.getTagReads({
      page, page_size: PAGE_SIZE, ...(warehouseId ? { warehouse_id: warehouseId } : {}),
    }),
    placeholderData: prev => prev,
  })

  const clearMut = useMutation({
    mutationFn: () => hardwareApi.clearTagReads(warehouseId || undefined),
    onSuccess: (res) => {
      toast.success(`${res.deleted} lectura(s) eliminada(s) del historial`)
      setPage(1)
      qc.invalidateQueries({ queryKey: ['rfid-tag-reads'] })
      qc.invalidateQueries({ queryKey: ['rfid-dashboard'] })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'No se pudo limpiar el historial'),
  })

  const handleClear = () => {
    const scope = warehouseId ? 'de esta bodega' : 'de TODAS las bodegas'
    if (confirm(`¿Eliminar permanentemente el historial de lecturas ${scope}? Esta acción no se puede deshacer.`)) {
      clearMut.mutate()
    }
  }

  return (
    <Card padding={false}>
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <CardTitle className="text-lg">Historial de Lecturas</CardTitle>
        <Button size="sm" variant="secondary" disabled={!data?.total || clearMut.isPending}
          loading={clearMut.isPending} onClick={handleClear}>
          <Trash2 className="h-4 w-4" /> Limpiar Historial
        </Button>
      </div>
      <Table>
        <Thead>
          <Tr>
            <Th>Fecha</Th><Th>EPC</Th><Th>Esquema</Th><Th>GTIN/SSCC</Th>
            <Th>Producto</Th><Th>RSSI</Th><Th>Estado</Th>
          </Tr>
        </Thead>
        <Tbody>
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <Tr key={i}>{Array.from({ length: 7 }).map((_, j) => (
                <Td key={j}><div className="h-4 bg-gray-100 rounded animate-pulse w-16" /></Td>
              ))}</Tr>
            ))
          ) : !data?.items.length ? (
            <EmptyRow cols={7} message="Sin lecturas registradas — simula una arriba o corre el gateway/simulador" />
          ) : (
            data.items.map(t => (
              <Tr key={t.id}>
                <Td className="text-xs text-gray-500">{fmt.datetime(t.read_at)}</Td>
                <Td className="font-mono text-xs">{t.epc_hex}</Td>
                <Td><span className="font-mono text-xs font-semibold text-primary-700">{t.epc_scheme}</span></Td>
                <Td className="font-mono text-xs">{t.gtin ?? t.sscc ?? '—'}</Td>
                <Td className="text-xs">{t.product_id ? `${t.product_id.slice(0, 8)}…` : <span className="text-gray-400">—</span>}</Td>
                <Td className="text-xs text-gray-500">{t.rssi_dbm != null ? `${t.rssi_dbm} dBm` : '—'}</Td>
                <Td><Badge status={t.processed ? 'confirmed' : 'pending'} label={t.processed ? 'Procesada' : 'Pendiente'} /></Td>
              </Tr>
            ))
          )}
        </Tbody>
      </Table>
      <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPageChange={setPage} />
    </Card>
  )
}
