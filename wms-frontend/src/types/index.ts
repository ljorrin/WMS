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
  avatar_url?: string
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
export type POStatus = 'draft' | 'confirmed' | 'partially_received' | 'closed' | 'cancelled'
export type GRNStatus = 'in_progress' | 'confirmed' | 'putaway_in_progress' | 'completed' | 'rejected'
export type QCStatus = 'pending' | 'in_progress' | 'approved' | 'rejected'
export type PutawayStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export interface PurchaseOrder {
  id: string
  po_number: string
  supplier_id: string
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
  quantity_received: number
  quantity_rejected: number
  location_id: string
  batch_number?: string
  expiry_date?: string
}

export interface PutawayTask {
  id: string
  product_id: string
  quantity: number
  from_location_id: string
  suggested_location_id?: string
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
  product_id: string
  quantity_requested: number
  quantity_picked: number
  quantity_short: number
  from_location_id: string
  status: PickingStatus
  priority: number
  assigned_to_id?: string
  cycle_time_seconds?: number
}

export type ShipmentStatusType =
  | 'pending' | 'ready' | 'in_transit' | 'delivered' | 'failed' | 'returned'

export interface Shipment {
  id: string
  shipment_number: string
  so_id: string
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
export type QCStatusType =
  | 'pending' | 'in_progress' | 'passed' | 'failed' | 'partial' | 'conditionally_released'

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
  pack_task_number: string
  status: PackStatusType
  box_type?: string
  box_count: number
  total_weight_kg?: number
  total_volume_m3?: number
  sscc?: string
  assigned_to_id?: string
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
  customer_id: string
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
