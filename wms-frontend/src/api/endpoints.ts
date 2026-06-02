// ═══════════════════════════════════════════════════════
// WMS Panama — Endpoints API centralizados
// ═══════════════════════════════════════════════════════
import api from './client'
import type {
  TokenResponse, User, PaginatedResponse,
  InventoryLevel, StockSummary,
  InventoryAdjustment, PurchaseOrder, GoodsReceipt,
  PutawayTask, SalesOrder, PickingWave, PickingTask,
  Shipment, InboundMetrics, OutboundMetrics,
  Warehouse, MovementRow, BatchListResponse,
  QualityInspection, PackTask, ReturnOrder,
  ThroughputResponse, InboundThroughputPoint, OutboundThroughputPoint,
  Product, Supplier, LocationLite,
} from '@/types'

interface ListResponse<T> { items: T[]; total: number; page: number; page_size: number }

// ── AUTH ──────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }).then(r => r.data),

  logout: (refresh_token: string) =>
    api.post('/auth/logout', { refresh_token }),

  me: () =>
    api.get<User>('/auth/me').then(r => r.data),

  refresh: (refresh_token: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token }).then(r => r.data),

  changePassword: (current_password: string, new_password: string) =>
    api.post('/auth/password/change', { current_password, new_password }),
}

// ── HEALTH ────────────────────────────────────────────
export const healthApi = {
  check: () => api.get('/health').then(r => r.data),
}

// ── WAREHOUSES ────────────────────────────────────────
export const warehouseApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Warehouse>>('/warehouses', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<Warehouse>(`/warehouses/${id}`).then(r => r.data),
}

// ── MASTER DATA ───────────────────────────────────────
export const masterApi = {
  getProducts: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Product>>('/master/products', { params }).then(r => r.data),

  getSuppliers: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Supplier>>('/master/suppliers', { params }).then(r => r.data),

  getLocations: (params?: Record<string, unknown>) =>
    api.get<ListResponse<LocationLite>>('/master/locations', { params }).then(r => r.data),
}

// ── INVENTORY ─────────────────────────────────────────
export const inventoryApi = {
  getStock: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<InventoryLevel>>('/inventory/stock', { params }).then(r => r.data),

  getProductSummary: (productId: string) =>
    api.get<StockSummary>(`/inventory/stock/${productId}/summary`).then(r => r.data),

  getMovements: (params?: Record<string, unknown>) =>
    api.get<ListResponse<MovementRow>>('/inventory/movements', { params }).then(r => r.data),

  getKardex: (productId: string, locationId?: string) =>
    api.get<MovementRow[]>('/inventory/movements/kardex', {
      params: { product_id: productId, location_id: locationId },
    }).then(r => r.data),

  getAdjustments: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<InventoryAdjustment>>('/inventory/adjustments', { params }).then(r => r.data),

  createAdjustment: (data: unknown) =>
    api.post<InventoryAdjustment>('/inventory/adjustments', data).then(r => r.data),

  approveAdjustment: (id: string) =>
    api.post(`/inventory/adjustments/${id}/approve`).then(r => r.data),

  applyAdjustment: (id: string) =>
    api.post(`/inventory/adjustments/${id}/apply`).then(r => r.data),

  getNearExpiry: (warehouseId: string, daysAhead = 30) =>
    api.get<BatchListResponse>('/inventory/batches/near-expiry', {
      params: { warehouse_id: warehouseId, days_ahead: daysAhead },
    }).then(r => r.data),

  getExpired: (warehouseId: string) =>
    api.get<BatchListResponse>('/inventory/batches/expired', {
      params: { warehouse_id: warehouseId },
    }).then(r => r.data),
}

// ── INBOUND ───────────────────────────────────────────
export const inboundApi = {
  // Purchase Orders
  getPOs: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<PurchaseOrder>>('/inbound/purchase-orders', { params }).then(r => r.data),

  getPO: (id: string) =>
    api.get<PurchaseOrder>(`/inbound/purchase-orders/${id}`).then(r => r.data),

  createPO: (data: unknown) =>
    api.post<PurchaseOrder>('/inbound/purchase-orders', data).then(r => r.data),

  updatePO: (id: string, data: unknown) =>
    api.put<PurchaseOrder>(`/inbound/purchase-orders/${id}`, data).then(r => r.data),

  confirmPO: (id: string) =>
    api.post(`/inbound/purchase-orders/${id}/confirm`),

  cancelPO: (id: string) =>
    api.post(`/inbound/purchase-orders/${id}/cancel`),

  deletePO: (id: string) =>
    api.delete(`/inbound/purchase-orders/${id}`),

  // GRN
  getGRNs: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<GoodsReceipt>>('/inbound/grn', { params }).then(r => r.data),

  getGRN: (id: string) =>
    api.get<GoodsReceipt>(`/inbound/grn/${id}`).then(r => r.data),

  createGRN: (data: unknown) =>
    api.post<GoodsReceipt>('/inbound/grn', data).then(r => r.data),

  confirmGRN: (id: string) =>
    api.post(`/inbound/grn/${id}/confirm`),

  // Quality Inspections
  getQCInspections: (params?: Record<string, unknown>) =>
    api.get<ListResponse<QualityInspection>>('/inbound/quality-inspections', { params }).then(r => r.data),

  getQCInspection: (id: string) =>
    api.get<QualityInspection>(`/inbound/quality-inspections/${id}`).then(r => r.data),

  resolveQC: (id: string, data: unknown) =>
    api.post(`/inbound/quality-inspections/${id}/resolve`, data).then(r => r.data),

  // Putaway
  getPutawayTasks: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<PutawayTask>>('/inbound/putaway', { params }).then(r => r.data),

  startPutaway: (id: string) =>
    api.post(`/inbound/putaway/${id}/start`).then(r => r.data),

  completePutaway: (id: string, actual_location_id: string, override_reason?: string) =>
    api.post(`/inbound/putaway/${id}/complete`, { actual_location_id, override_reason }).then(r => r.data),

  // Dashboard
  getDashboard: (warehouseId?: string) =>
    api.get<InboundMetrics>('/inbound/dashboard', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  getThroughput: (days = 7, warehouseId?: string) =>
    api.get<ThroughputResponse<InboundThroughputPoint>>('/inbound/dashboard/throughput', {
      params: { days, ...(warehouseId ? { warehouse_id: warehouseId } : {}) },
    }).then(r => r.data),
}

// ── OUTBOUND ──────────────────────────────────────────
export const outboundApi = {
  // Sales Orders
  getSOs: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<SalesOrder>>('/outbound/orders', { params }).then(r => r.data),

  getSO: (id: string) =>
    api.get<SalesOrder>(`/outbound/orders/${id}`).then(r => r.data),

  createSO: (data: unknown) =>
    api.post<SalesOrder>('/outbound/orders', data).then(r => r.data),

  confirmSO: (id: string) =>
    api.post(`/outbound/orders/${id}/confirm`),

  cancelSO: (id: string, reason: string) =>
    api.post(`/outbound/orders/${id}/cancel`, { reason }),

  // Waves
  getWaves: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<PickingWave>>('/outbound/waves', { params }).then(r => r.data),

  createWave: (data: unknown) =>
    api.post<PickingWave>('/outbound/waves', data).then(r => r.data),

  releaseWave: (id: string) =>
    api.post(`/outbound/waves/${id}/release`).then(r => r.data),

  // Picking
  getPickingTasks: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<PickingTask>>('/outbound/picking', { params }).then(r => r.data),

  startPick: (id: string) =>
    api.post(`/outbound/picking/${id}/start`).then(r => r.data),

  completePick: (id: string, data: unknown) =>
    api.post(`/outbound/picking/${id}/complete`, data).then(r => r.data),

  // Packing
  getPackTasks: (params?: Record<string, unknown>) =>
    api.get<ListResponse<PackTask>>('/outbound/packing', { params }).then(r => r.data),

  startPack: (id: string) =>
    api.post(`/outbound/packing/${id}/start`).then(r => r.data),

  completePack: (id: string, data: unknown) =>
    api.post(`/outbound/packing/${id}/complete`, data).then(r => r.data),

  // Shipments
  getShipments: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Shipment>>('/outbound/shipments', { params }).then(r => r.data),

  createShipment: (data: unknown) =>
    api.post<Shipment>('/outbound/shipments', data).then(r => r.data),

  dispatchShipment: (id: string, data: unknown) =>
    api.post(`/outbound/shipments/${id}/dispatch`, data).then(r => r.data),

  deliverShipment: (id: string, data: unknown) =>
    api.post(`/outbound/shipments/${id}/deliver`, data).then(r => r.data),

  // Returns (RMA)
  getReturns: (params?: Record<string, unknown>) =>
    api.get<ListResponse<ReturnOrder>>('/outbound/returns', { params }).then(r => r.data),

  getReturn: (id: string) =>
    api.get<ReturnOrder>(`/outbound/returns/${id}`).then(r => r.data),

  createReturn: (data: unknown) =>
    api.post<ReturnOrder>('/outbound/returns', data).then(r => r.data),

  receiveReturn: (id: string, data: unknown) =>
    api.post(`/outbound/returns/${id}/receive`, data).then(r => r.data),

  // Dashboard
  getDashboard: (warehouseId?: string) =>
    api.get<OutboundMetrics>('/outbound/dashboard', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  getThroughput: (days = 7, warehouseId?: string) =>
    api.get<ThroughputResponse<OutboundThroughputPoint>>('/outbound/dashboard/throughput', {
      params: { days, ...(warehouseId ? { warehouse_id: warehouseId } : {}) },
    }).then(r => r.data),
}
