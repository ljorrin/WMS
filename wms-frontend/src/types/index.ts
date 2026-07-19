// ═══════════════════════════════════════════════════════
// WMS Panama — Tipos globales TypeScript
// ═══════════════════════════════════════════════════════

// ── Auth ─────────────────────────────────────────────
export interface User {
  id: string
  email: string
  full_name: string
  username: string
  tenant_id: string
  roles: string[]
  permissions: string[]
  is_active: boolean
  is_superadmin?: boolean
  avatar_url?: string
  mfa_enabled?: boolean
}

export interface Company {
  id: string
  name: string
  legal_name?: string | null
  ruc?: string | null
  dv?: string | null
  email?: string | null
  phone?: string | null
  address?: string | null
  city?: string | null
  country: string
  gs1_company_prefix?: string | null
  gln?: string | null
  logo_url?: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// ── Pagination ────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PaginationParams {
  page?: number
  page_size?: number
}

// ── Common ────────────────────────────────────────────
export interface ApiError {
  detail: string | { msg: string; loc: string[] }[]
}

// ── Inventory ─────────────────────────────────────────
export interface InventoryLevel {
  id: string
  product_id: string
  product_name?: string
  product_sku?: string
  location_id: string
  location_code?: string
  warehouse_id: string
  batch_id?: string
  batch_number?: string
  expiry_date?: string
  quantity_on_hand: number
  quantity_available: number
  quantity_reserved: number
  quantity_on_order: number
  uom_id: string
  uom_code?: string
  status: 'active' | 'quarantine' | 'damaged' | 'expired'
  updated_at: string
}

export interface StockSummary {
  product_id: string
  product_name: string
  product_sku: string
  total_on_hand: number
  total_available: number
  total_reserved: number
  locations_count: number
  batches_count: number
}

export interface InventoryMovement {
  id: string
  movement_type: string
  product_id: string
  product_name?: string
  location_id: string
  location_code?: string
  quantity: number
  uom_code?: string
  reference: string
  notes?: string
  created_by_id: string
  created_at: string
  balance?: number
}

export interface InventoryAdjustment {
  id: string
  adjustment_number: string
  status: 'draft' | 'pending_approval' | 'approved' | 'applied' | 'rejected'
  reason: string
  notes?: string
  lines: AdjustmentLine[]
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface AdjustmentLine {
  id: string
  product_id: string
  location_id: string
  quantity_system: number
  quantity_counted: number
  variance: number
}

// ── Inbound ───────────────────────────────────────────
export type POStatus = 'draft' | 'confirmed' | 'sent' | 'partially_received' | 'received' | 'closed' | 'cancelled'
export type GRNStatus = 'draft' | 'in_progress' | 'confirmed' | 'putaway_in_progress' | 'completed' | 'rejected' | 'cancelled'
export type QCStatus = 'pending' | 'in_progress' | 'approved' | 'rejected' | 'partial' | 'cancelled'
export type PutawayStatus = 'pending' | 'assigned' | 'in_progress' | 'completed' | 'cancelled'

export interface PurchaseOrder {
  id: string
  po_number: string
  supplier_id: string
  supplier_name?: string
  warehouse_id: string
  status: POStatus
  order_date: string
  expected_delivery_date?: string
  supplier_po_reference?: string
  payment_terms?: string
  incoterms?: string
  notes?: string
  erp_reference?: string
  total_amount: number
  currency: string
  lines: POLine[]
  status_history?: POStatusHistory[]
  created_at: string
  updated_at: string
}

export interface POLine {
  id: string
  product_id: string
  product_sku?: string
  product_name?: string
  quantity_ordered: number
  quantity_received: number
  quantity_pending: number
  unit_cost: number
  status: string
}

export interface POStatusHistory {
  id: string
  from_status?: string | null
  to_status: string
  changed_by_id?: string | null
  reason?: string | null
  created_at: string
}

export interface PurchaseOrderUpdate {
  supplier_po_reference?: string
  expected_delivery_date?: string
  payment_terms?: string
  incoterms?: string
  notes?: string
  erp_reference?: string
}

export interface GoodsReceipt {
  id: string
  grn_number: string
  po_id?: string
  asn_id?: string
  warehouse_id: string
  status: GRNStatus
  receiving_mode?: string
  dock_number?: string
  requires_qc: boolean
  ambient_temp_celsius?: number
  product_temp_celsius?: number
  received_at: string
  confirmed_at?: string
  notes?: string
  lines: GRNLine[]
}

export interface GRNLine {
  id: string
  product_id: string
  product_sku?: string
  product_name?: string
  quantity_received: number
  quantity_rejected: number
  location_id: string
  location_code?: string
  batch_number?: string
  expiry_date?: string
}

export interface PutawayTask {
  id: string
  product_id: string
  product_sku?: string
  product_name?: string
  quantity: number
  from_location_id: string
  from_location_code?: string
  suggested_location_id?: string
  suggested_location_code?: string
  actual_location_id?: string
  status: PutawayStatus
  priority: number
  assigned_to_id?: string
  cycle_time_seconds?: number
  created_at: string
}

// ── Master Data ───────────────────────────────────────
export interface Product {
  id: string
  sku: string
  name: string
  uom: string
  status: string
  gtin_13?: string | null
}

export interface Supplier {
  id: string
  code: string
  name: string
  status: string
  supplier_type: string
  lead_time_days?: number | null
}

export interface Customer {
  id: string
  code: string
  name: string
  customer_type: string
  is_active: boolean
  contact_email?: string | null
  delivery_city?: string | null
}

export interface BoxType {
  id: string
  code: string
  name: string
  description?: string | null
  is_active: boolean
  length_cm?: number | null
  width_cm?: number | null
  height_cm?: number | null
  max_weight_kg?: number | null
}

export interface LocationLite {
  id: string
  code: string
  warehouse_id: string
  location_type: string
  status: string
}

// ── Outbound ──────────────────────────────────────────
export type SOStatus = 'draft' | 'confirmed' | 'allocated' | 'picking' | 'packed' | 'shipped' | 'delivered' | 'cancelled' | 'partially_shipped'
export type PickingStatus = 'pending' | 'in_progress' | 'completed' | 'short_picked' | 'cancelled'
export type WaveStatus = 'open' | 'released' | 'in_progress' | 'completed' | 'cancelled'

export interface SalesOrder {
  id: string
  so_number: string
  customer_id: string
  customer_name?: string
  warehouse_id: string
  status: SOStatus
  priority: number
  order_date: string
  requested_delivery_date?: string
  total_amount: number
  currency: string
  wave_id?: string
  lines: SOLine[]
  created_at: string
  updated_at: string
}

export interface SOLine {
  id: string
  product_id: string
  product_name?: string
  quantity_ordered: number
  quantity_picked: number
  quantity_shipped: number
  quantity_backordered: number
  unit_price: number
  status: string
}

export interface PickingWave {
  id: string
  wave_number: string
  status: WaveStatus
  picking_method: string
  priority: number
  total_orders: number
  total_lines: number
  total_units: number
  released_at?: string
  completed_at?: string
}

export interface PickingTask {
  id: string
  so_id: string
  wave_id?: string
  product_id: string
  product_name?: string
  quantity_requested: number
  quantity_picked: number
  quantity_short: number
  from_location_id: string
  from_location_code?: string
  to_location_id?: string
  status: PickingStatus
  priority: number
  assigned_to_id?: string
  cycle_time_seconds?: number
  started_at?: string
  completed_at?: string
}

export type ShipmentStatusType =
  | 'pending' | 'ready' | 'in_transit' | 'delivered' | 'failed' | 'returned'

export interface Shipment {
  id: string
  shipment_number: string
  so_id: string
  so_number?: string
  customer_name?: string
  warehouse_id: string
  status: ShipmentStatusType
  carrier_type?: string
  carrier_name?: string
  tracking_number?: string
  vehicle_plate?: string
  driver_name?: string
  scheduled_pickup?: string
  actual_pickup?: string
  estimated_delivery?: string
  actual_delivery?: string
  total_boxes: number
  total_weight_kg?: number
  delivery_note_number?: string
  delivered_to_name?: string
  is_export: boolean
  notes?: string
  created_at: string
}

// ── Dashboard KPIs ─────────────────────────────────────
export interface InboundMetrics {
  pos_open: number
  pos_overdue: number
  grns_today: number
  grns_pending_qc: number
  grns_pending_putaway: number
  avg_defect_rate_pct: number
  rtv_pending: number
  avg_putaway_cycle_time_seconds?: number
  putaway_tasks_open: number
}

export interface OutboundMetrics {
  orders_open: number
  orders_pending_pick: number
  orders_pending_pack: number
  orders_pending_ship: number
  orders_overdue: number
  picks_today: number
  avg_pick_cycle_time_seconds?: number
  waves_open: number
  shipments_today: number
  shipments_in_transit: number
  on_time_delivery_pct?: number
  short_pick_rate_pct?: number
  rma_open: number
  order_fill_rate_pct?: number
}

export interface InventoryMetrics {
  distinct_skus: number
  stock_positions: number
  total_stock_value?: number
  near_expiry_batches: number
  expired_batches: number
  active_alerts: number
  pending_adjustments: number
  movements_today: number
}

// ── Throughput (series para gráficas) ─────────────────
export interface InboundThroughputPoint {
  day: string
  grns: number
  putaway_completed: number
}

export interface OutboundThroughputPoint {
  day: string
  picks: number
  shorts: number
  shipments: number
}

export interface ThroughputResponse<T> {
  series: T[]
}

// ── Warehouse ─────────────────────────────────────────
export interface Warehouse {
  id: string
  code: string
  name: string
  type: string
  status: string
  city?: string
  province?: string
  country: string
  has_cold_storage: boolean
  picking_strategy: string
  default_picking_method: string
}

// ── Movements (lista paginada del backend) ────────────
export interface MovementRow {
  id: string
  movement_type: string
  product_id: string
  product_name?: string
  location_id: string
  location_code?: string
  warehouse_id: string
  quantity: number
  uom_code?: string
  reference_type?: string
  reference_id?: string
  batch_number?: string
  notes?: string
  created_by_id?: string
  created_at: string
}

// ── Batches próximos a vencer ─────────────────────────
export interface Batch {
  id: string
  product_id: string
  warehouse_id: string
  lot_number: string
  expiry_date?: string
  manufacture_date?: string
  supplier_lot?: string
  quantity_received: number
  quantity_available: number
  quantity_on_hold: number
  days_to_expiry?: number
  is_expired: boolean
  is_near_expiry: boolean
  status: string
  created_at: string
}

export interface BatchListResponse {
  items: Batch[]
  total: number
  days_ahead?: number
  warning?: string
}

// ── Quality Inspection (QC) ───────────────────────────
export type QCStatusType = QCStatus

export interface QCLine {
  id: string
  qi_id: string
  line_number: number
  grn_line_id: string
  product_id: string
  quantity_inspected: number
  quantity_approved: number
  quantity_rejected: number
  defect_codes?: string[]
  defect_description?: string
  notes?: string
}

export interface QualityInspection {
  id: string
  grn_id: string
  qi_number: string
  status: QCStatusType
  aql_level?: string
  sample_size?: number
  inspection_type?: string
  total_inspected?: number
  total_approved?: number
  total_rejected?: number
  defect_rate?: number
  disposition?: string
  disposition_notes?: string
  inspection_date?: string
  completed_at?: string
  notes?: string
  lines: QCLine[]
  inspector_id?: string
  created_at: string
  updated_at: string
}

// ── Pack Task ─────────────────────────────────────────
export type PackStatusType = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export interface PackTask {
  id: string
  so_id: string
  so_number?: string
  shipment_id?: string
  pack_task_number: string
  status: PackStatusType
  box_type?: string
  box_count: number
  total_weight_kg?: number
  total_volume_m3?: number
  sscc?: string
  assigned_to_id?: string
  assigned_to_name?: string
  started_at?: string
  completed_at?: string
  cycle_time_seconds?: number
  label_printed: boolean
  packing_list_printed: boolean
  notes?: string
  created_at: string
  updated_at: string
}

// ── Return Order (RMA) ────────────────────────────────
export type RMAStatus =
  | 'requested' | 'approved' | 'in_transit' | 'received' | 'inspected' | 'closed' | 'rejected'

export interface ReturnOrder {
  id: string
  warehouse_id: string
  so_id?: string
  so_number?: string
  customer_id: string
  customer_name?: string
  rma_number: string
  status: RMAStatus
  reason: string
  return_type: string
  received_at?: string
  received_by_id?: string
  inspection_notes?: string
  restocking_eligible: boolean
  restocking_location_id?: string
  refund_amount: number
  refund_issued_at?: string
  credit_memo_number?: string
  notes?: string
  created_at: string
  updated_at: string
}

// ── RTV (Devolución a Proveedor) ──────────────────────
export type RTVStatus = 'pending' | 'approved' | 'shipped' | 'credit_received' | 'closed' | 'cancelled'

export interface ReturnToVendor {
  id: string
  tenant_id: string
  grn_id?: string
  supplier_id: string
  supplier_name?: string
  warehouse_id: string
  rtv_number: string
  status: RTVStatus
  reason: string
  notes?: string
  return_carrier?: string
  return_tracking?: string
  shipped_at?: string
  confirmed_at?: string
  credit_expected: number
  credit_received: number
  currency: string
  credit_memo_number?: string
  created_by_id: string
  created_at: string
  updated_at: string
}

// ── Conteo Cíclico ─────────────────────────────────────
export type CycleCountStatus = 'draft' | 'in_progress' | 'completed' | 'cancelled'

export interface CycleCountLineRow {
  id: string
  location_id: string
  product_id: string
  batch_id?: string
  lot_number?: string
  quantity_system?: number
  quantity_counted?: number
  variance?: number
  variance_pct?: number
  status: string
  counted_at?: string
  counted_by?: string
  location_code?: string
  product_code?: string
  product_name?: string
}

export interface CycleCount {
  id: string
  tenant_id: string
  warehouse_id: string
  count_number: string
  name: string
  count_type: string
  status: CycleCountStatus
  scheduled_date?: string
  started_at?: string
  completed_at?: string
  notes?: string
  lines: CycleCountLineRow[]
  total_lines: number
  counted_lines: number
  discrepancy_lines: number
  accuracy_pct?: number
  created_at: string
}

// ── Reservas de Inventario ─────────────────────────────
export interface InventoryReservation {
  id: string
  warehouse_id: string
  product_id: string
  product_name?: string
  quantity: number
  reservation_type: string
  reference_type: string
  reference_id: string
  reference_number: string
  batch_id?: string
  location_id?: string
  expires_at?: string
  created_at: string
}

// ── Labor Management (FR-090…093) ──────────────────────
export type LaborActivityType =
  | 'pick' | 'putaway' | 'receive' | 'pack' | 'cycle_count'
  | 'replenish' | 'loading' | 'unloading' | 'transfer'

export type LaborTaskStatus = 'pending' | 'assigned' | 'in_progress' | 'completed' | 'cancelled'

export interface LaborStandard {
  id: string
  warehouse_id?: string | null
  activity_type: LaborActivityType
  uom: string
  fixed_minutes: number
  std_minutes_per_unit: number
  description?: string | null
  is_active: boolean
}

export interface LaborTask {
  id: string
  warehouse_id: string
  user_id?: string | null
  activity_type: LaborActivityType
  reference_type?: string | null
  reference_id?: string | null
  reference_number?: string | null
  location_id?: string | null
  zone?: string | null
  priority: number
  quantity: number
  uom: string
  status: LaborTaskStatus
  assigned_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  actual_minutes?: number | null
  standard_minutes?: number | null
  performance_pct?: number | null
  is_interleaved: boolean
}

export interface LaborActivityKPI {
  activity_type: string
  tasks_completed: number
  avg_performance_pct?: number | null
  total_standard_hours: number
  total_actual_hours: number
}

export interface LaborOperatorKPI {
  user_id: string
  tasks_completed: number
  avg_performance_pct?: number | null
  total_actual_hours: number
}

export interface LaborDashboardMetrics {
  window_days: number
  tasks_completed: number
  tasks_pending: number
  tasks_in_progress: number
  avg_performance_pct?: number | null
  total_standard_hours: number
  total_actual_hours: number
  labor_efficiency_pct?: number | null
  by_activity: LaborActivityKPI[]
  top_operators: LaborOperatorKPI[]
  bottom_operators: LaborOperatorKPI[]
}

// ── Slotting Dinámico (FR-094…097) ─────────────────────
export type SlottingRecommendationStatus = 'pending' | 'applied' | 'rejected' | 'expired'

export interface SlottingPolicy {
  id: string
  warehouse_id?: string | null
  strategy: string
  velocity_window_days: number
  abc_a_threshold: number
  abc_b_threshold: number
  golden_zone_code?: string | null
  bulk_zone_code?: string | null
  is_active: boolean
}

export interface SlottingRecommendation {
  id: string
  warehouse_id: string
  product_id: string
  product_name?: string
  abc_class?: string | null
  velocity_score?: number | null
  pick_count?: number | null
  current_location_id?: string | null
  current_zone_code?: string | null
  recommended_location_id?: string | null
  recommended_zone_code?: string | null
  reason?: string | null
  score_delta?: number | null
  status: SlottingRecommendationStatus
  applied_at?: string | null
}

export interface SlottingAnalyzeResult {
  window_days: number
  products_analyzed: number
  abc_counts: Record<string, number>
  recommendations_created: number
  golden_zone?: string | null
  bulk_zone?: string | null
}

export interface SlottingDashboardMetrics {
  pending: number
  applied: number
  rejected: number
  pending_by_class: Record<string, number>
  estimated_travel_savings: number
}

// ── Order Streaming / Waveless (FR-055) ────────────────
export interface StreamingTask {
  id: string
  so_id: string
  so_line_id: string
  product_id: string
  product_name?: string
  quantity_requested: number
  from_location_id?: string | null
  status: string
  priority: number
  assigned_to_id?: string | null
  wave_id?: string | null
  started_at?: string | null
}

export interface StreamingMetrics {
  queue_pending: number
  in_progress: number
  operators_active: number
  wip_by_operator: Record<string, number>
}

// ── Hardware RFID/RF + Etiquetas ZPL (Fase 2) ──────────
export interface RfidReader {
  id: string
  warehouse_id: string
  code: string
  name: string
  vendor?: string | null
  model?: string | null
  ip_address?: string | null
  port: number
  protocol: string
  status: string
  last_seen_at?: string | null
  notes?: string | null
}

export interface RfidAntenna {
  id: string
  reader_id: string
  antenna_number: number
  name: string
  location_id?: string | null
  zone_id?: string | null
  transmit_power_dbm?: number | null
  is_active: boolean
}

export interface RfidTagRead {
  id: string
  warehouse_id: string
  reader_id: string
  antenna_id?: string | null
  epc_hex: string
  epc_scheme: string
  gtin?: string | null
  sscc?: string | null
  serial?: number | null
  product_id?: string | null
  rssi_dbm?: number | null
  read_at: string
  processed: boolean
  process_notes?: string | null
}

export interface RfidDashboardMetrics {
  readers_by_status: Record<string, number>
  reads_today: number
  unique_epcs_today: number
  unprocessed_reads: number
}

export interface ZplLabelResult {
  zpl: string
  epc_hex?: string | null
  epc_uri?: string | null
}

// ── Asistente IA agéntico (Fase 5) ─────────────────────
export interface ToolCallTrace {
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
}

export interface ChatResponse {
  conversation_id: string
  response: string
  sources: ToolCallTrace[]
  latency_ms: number
  tokens_used: number
}

export interface AIConversation {
  id: string
  title?: string | null
  context_type?: string | null
  message_count: number
  total_tokens: number
  created_at: string
  updated_at: string
}

export interface AIConversationMessage {
  id: string
  role: string
  content: string
  sources: ToolCallTrace[]
  tokens_used: number
  latency_ms?: number | null
  created_at: string
}

export interface AIConversationDetail extends AIConversation {
  messages: AIConversationMessage[]
}
