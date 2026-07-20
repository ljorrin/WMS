// ═══════════════════════════════════════════════════════
// WMS Panama — Endpoints API centralizados
// ═══════════════════════════════════════════════════════
import api from './client'
import type {
  TokenResponse, User, PaginatedResponse,
  InventoryLevel, StockSummary,
  InventoryAdjustment, PurchaseOrder, GoodsReceipt,
  PutawayTask, SalesOrder, PickingWave, PickingTask,
  Shipment, InboundMetrics, OutboundMetrics, InventoryMetrics,
  Warehouse, MovementRow, BatchListResponse,
  QualityInspection, PackTask, ReturnOrder,
  ThroughputResponse, InboundThroughputPoint, OutboundThroughputPoint,
  Product, Supplier, Customer, BoxType, LocationLite,
  ReturnToVendor, CycleCount, InventoryReservation, Company,
  LaborStandard, LaborTask, LaborDashboardMetrics,
  SlottingPolicy, SlottingRecommendation, SlottingAnalyzeResult, SlottingDashboardMetrics,
  StreamingTask, StreamingMetrics,
  RfidReader, RfidAntenna, RfidTagRead, RfidDashboardMetrics, ZplLabelResult,
  ChatResponse, AIConversation, AIConversationDetail,
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

  // MFA / 2FA (FR-001)
  mfaEnroll: () =>
    api.post<{ secret: string; otpauth_uri: string; message: string }>('/auth/mfa/enroll').then(r => r.data),

  mfaVerify: (code: string) =>
    api.post<{ mfa_enabled: boolean; message: string }>('/auth/mfa/verify', { code }).then(r => r.data),

  mfaDisable: (code: string) =>
    api.post<{ mfa_enabled: boolean; message: string }>('/auth/mfa/disable', { code }).then(r => r.data),
}

// ── HEALTH ────────────────────────────────────────────
export const healthApi = {
  check: () => api.get('/health').then(r => r.data),
}

// ── INTEGRATIONS ──────────────────────────────────────
export const integrationsApi = {
  getStatus: () => api.get<Record<string, { configured: boolean, missing: string[], extra?: any }>>('/integrations/status').then(r => r.data),
}

// ── WAREHOUSES ────────────────────────────────────────
export const warehouseApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<ListResponse<Warehouse>>('/warehouses', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<Warehouse>(`/warehouses/${id}`).then(r => r.data),

  create: (data: unknown) =>
    api.post<Warehouse>('/warehouses', data).then(r => r.data),

  update: (id: string, data: unknown) =>
    api.put<Warehouse>(`/warehouses/${id}`, data).then(r => r.data),

  listCompanies: () =>
    api.get<Company[]>('/warehouses/companies').then(r => r.data),

  createCompany: (data: unknown) =>
    api.post<Company>('/warehouses/companies', data).then(r => r.data),

  updateCompany: (id: string, data: unknown) =>
    api.put<Company>(`/warehouses/companies/${id}`, data).then(r => r.data),
}

// ── MASTER DATA ───────────────────────────────────────
export const masterApi = {
  getProducts: (params?: Record<string, unknown>) => {
    const p = params ? Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== '')) : {}
    return api.get<ListResponse<Product>>('/master/products', { params: p }).then(r => r.data)
  },

  getSuppliers: (params?: Record<string, unknown>) => {
    const p = params ? Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== '')) : {}
    return api.get<ListResponse<Supplier>>('/master/suppliers', { params: p }).then(r => r.data)
  },

  getCustomers: (params?: Record<string, unknown>) => {
    const p = params ? Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== '')) : {}
    return api.get<ListResponse<Customer>>('/master/customers', { params: p }).then(r => r.data)
  },

  getBoxTypes: (params?: Record<string, unknown>) => {
    const p = params ? Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== '')) : {}
    return api.get<ListResponse<BoxType>>('/master/box-types', { params: p }).then(r => r.data)
  },

  getLocations: (params?: Record<string, unknown>) => {
    const p = params ? Object.fromEntries(Object.entries(params).filter(([_, v]) => v !== '')) : {}
    return api.get<ListResponse<LocationLite>>('/master/locations', { params: p }).then(r => r.data)
  },

  // Alta / edición / carga masiva (FR-010/012/013/014/015)
  createProduct: (data: unknown) =>
    api.post<Product>('/master/products', data).then(r => r.data),
  updateProduct: (id: string, data: unknown) =>
    api.put<Product>(`/master/products/${id}`, data).then(r => r.data),
  bulkImportProducts: (data: { dry_run: boolean; rows: unknown[] }) =>
    api.post('/master/products/bulk-import', data).then(r => r.data),
  createSupplier: (data: unknown) =>
    api.post<Supplier>('/master/suppliers', data).then(r => r.data),
  updateSupplier: (id: string, data: unknown) =>
    api.put<Supplier>(`/master/suppliers/${id}`, data).then(r => r.data),
  createCustomer: (data: unknown) =>
    api.post<Customer>('/master/customers', data).then(r => r.data),
  updateCustomer: (id: string, data: unknown) =>
    api.put<Customer>(`/master/customers/${id}`, data).then(r => r.data),
  createBoxType: (data: unknown) =>
    api.post<BoxType>('/master/box-types', data).then(r => r.data),
  updateBoxType: (id: string, data: unknown) =>
    api.put<BoxType>(`/master/box-types/${id}`, data).then(r => r.data),
  createLocation: (data: unknown) =>
    api.post<LocationLite>('/master/locations', data).then(r => r.data),
  updateLocation: (id: string, data: unknown) =>
    api.put<LocationLite>(`/master/locations/${id}`, data).then(r => r.data),
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

  getNearExpiry: (warehouseId: string, daysAhead = 30, page = 1, pageSize = 25) =>
    api.get<BatchListResponse>('/inventory/batches/near-expiry', {
      params: { warehouse_id: warehouseId, days_ahead: daysAhead, page, page_size: pageSize },
    }).then(r => r.data),

  getExpired: (warehouseId: string, page = 1, pageSize = 25) =>
    api.get<BatchListResponse>('/inventory/batches/expired', {
      params: { warehouse_id: warehouseId, page, page_size: pageSize },
    }).then(r => r.data),

  getDashboard: (warehouseId?: string) =>
    api.get<InventoryMetrics>('/inventory/dashboard', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  // Transferencias
  transferStock: (data: unknown) =>
    api.post('/inventory/transfer', data).then(r => r.data),

  // Reservas
  getReservations: (params?: Record<string, unknown>) =>
    api.get<ListResponse<InventoryReservation>>('/inventory/reservations', { params }).then(r => r.data),

  createReservation: (data: unknown) =>
    api.post('/inventory/reservations', data).then(r => r.data),

  cancelReservation: (id: string) =>
    api.delete(`/inventory/reservations/${id}`),

  // Conteos Cíclicos
  getCycleCounts: (params?: Record<string, unknown>) =>
    api.get<ListResponse<CycleCount>>('/inventory/cycle-counts', { params }).then(r => r.data),

  getCycleCount: (id: string) =>
    api.get<CycleCount>(`/inventory/cycle-counts/${id}`).then(r => r.data),

  createCycleCount: (data: unknown) =>
    api.post<{ id: string; count_number: string; status: string; total_lines: number; message: string }>(
      '/inventory/cycle-counts', data
    ).then(r => r.data),

  recordCycleCountResults: (id: string, results: unknown[]) =>
    api.post(`/inventory/cycle-counts/${id}/results`, { results }).then(r => r.data),

  completeCycleCount: (id: string, applyResults: boolean) =>
    api.post(`/inventory/cycle-counts/${id}/complete`, { apply_results: applyResults }).then(r => r.data),
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

  completePutaway: (id: string, actual_location: string, override_reason?: string) =>
    api.post(`/inbound/putaway/${id}/complete`, { actual_location, override_reason }).then(r => r.data),

  // Dashboard
  getDashboard: (warehouseId?: string) =>
    api.get<InboundMetrics>('/inbound/dashboard', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  getThroughput: (days = 7, warehouseId?: string) =>
    api.get<ThroughputResponse<InboundThroughputPoint>>('/inbound/dashboard/throughput', {
      params: { days, ...(warehouseId ? { warehouse_id: warehouseId } : {}) },
    }).then(r => r.data),

  // RTV (Devolución a Proveedor)
  getRTVs: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<ReturnToVendor>>('/inbound/rtv', { params }).then(r => r.data),

  getRTV: (id: string) =>
    api.get<ReturnToVendor>(`/inbound/rtv/${id}`).then(r => r.data),

  createRTV: (data: unknown) =>
    api.post<ReturnToVendor>('/inbound/rtv', data).then(r => r.data),

  approveRTV: (id: string) =>
    api.post(`/inbound/rtv/${id}/approve`).then(r => r.data),

  shipRTV: (id: string, data: unknown) =>
    api.post(`/inbound/rtv/${id}/ship`, data).then(r => r.data),

  creditRTV: (id: string, params: { credit_memo_number: string, credit_received: number }) =>
    api.post(`/inbound/rtv/${id}/credit`, null, { params }).then(r => r.data),
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

  getPackTaskPackingListPdf: (id: string) =>
    api.get<Blob>(`/outbound/packing/${id}/packing-list`, { responseType: 'blob' }).then(r => r.data),

  getPackTaskLabelPdf: (id: string) =>
    api.get<Blob>(`/outbound/packing/${id}/label`, { responseType: 'blob' }).then(r => r.data),

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

  // Documento de despacho (FR-061): lista de empaque / remisión en PDF
  getPackingListPdf: (shipmentId: string) =>
    api.get<Blob>(`/outbound/shipments/${shipmentId}/packing-list`, { responseType: 'blob' }).then(r => r.data),
}

// ── LABOR MANAGEMENT (FR-090…093) ────────────────────
export const laborApi = {
  getStandards: (params?: Record<string, unknown>) =>
    api.get<ListResponse<LaborStandard>>('/labor/standards', { params }).then(r => r.data),

  createStandard: (data: unknown) =>
    api.post<LaborStandard>('/labor/standards', data).then(r => r.data),

  updateStandard: (id: string, data: unknown) =>
    api.put<LaborStandard>(`/labor/standards/${id}`, data).then(r => r.data),

  getTasks: (params?: Record<string, unknown>) =>
    api.get<ListResponse<LaborTask>>('/labor/tasks', { params }).then(r => r.data),

  createTask: (data: unknown) =>
    api.post<LaborTask>('/labor/tasks', data).then(r => r.data),

  assignTask: (id: string, operatorId: string) =>
    api.post<LaborTask>(`/labor/tasks/${id}/assign`, null, { params: { operator_id: operatorId } }).then(r => r.data),

  startTask: (id: string) =>
    api.post<LaborTask>(`/labor/tasks/${id}/start`).then(r => r.data),

  completeTask: (id: string) =>
    api.post<LaborTask>(`/labor/tasks/${id}/complete`).then(r => r.data),

  suggestNextTask: (warehouseId: string, zone?: string) =>
    api.get<LaborTask | null>('/labor/next-task', { params: { warehouse_id: warehouseId, zone } }).then(r => r.data),

  assignNextTask: (warehouseId: string, operatorId?: string, zone?: string) =>
    api.post<LaborTask | null>('/labor/next-task/assign', null, {
      params: { warehouse_id: warehouseId, operator_id: operatorId, zone },
    }).then(r => r.data),

  getDashboard: (warehouseId?: string, windowDays = 7) =>
    api.get<LaborDashboardMetrics>('/labor/dashboard', {
      params: { window_days: windowDays, ...(warehouseId ? { warehouse_id: warehouseId } : {}) },
    }).then(r => r.data),
}

// ── SLOTTING DINÁMICO (FR-094…097) ───────────────────
export const slottingApi = {
  getPolicies: () =>
    api.get<{ items: SlottingPolicy[] }>('/slotting/policy').then(r => r.data),

  upsertPolicy: (data: unknown) =>
    api.put<SlottingPolicy>('/slotting/policy', data).then(r => r.data),

  analyze: (warehouseId: string, windowDays?: number, persist = true) =>
    api.post<SlottingAnalyzeResult>('/slotting/analyze', {
      warehouse_id: warehouseId, window_days: windowDays, persist,
    }).then(r => r.data),

  getRecommendations: (params?: Record<string, unknown>) =>
    api.get<ListResponse<SlottingRecommendation>>('/slotting/recommendations', { params }).then(r => r.data),

  applyRecommendation: (id: string) =>
    api.post<SlottingRecommendation>(`/slotting/recommendations/${id}/apply`).then(r => r.data),

  rejectRecommendation: (id: string) =>
    api.post<SlottingRecommendation>(`/slotting/recommendations/${id}/reject`).then(r => r.data),

  getDashboard: (warehouseId?: string) =>
    api.get<SlottingDashboardMetrics>('/slotting/dashboard', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),
}

// ── ORDER STREAMING / WAVELESS (FR-055) ──────────────
export const streamingApi = {
  enqueueOrder: (soId: string) =>
    api.post<{ so_id: string; tasks_created: number; tasks: StreamingTask[] }>(
      '/streaming/enqueue', { so_id: soId }
    ).then(r => r.data),

  next: (warehouseId: string, operatorId?: string, currentPickSequence?: number, maxWip = 1) =>
    api.post<StreamingTask | null>('/streaming/next', {
      warehouse_id: warehouseId,
      operator_id: operatorId,
      current_pick_sequence: currentPickSequence,
      max_wip: maxWip,
    }).then(r => r.data),

  getQueue: (warehouseId?: string, limit = 50) =>
    api.get<{ items: StreamingTask[]; count: number }>('/streaming/queue', {
      params: { warehouse_id: warehouseId, limit },
    }).then(r => r.data),

  getMetrics: (warehouseId?: string) =>
    api.get<StreamingMetrics>('/streaming/metrics', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),
}

// ── HARDWARE RFID/RF + ETIQUETAS ZPL (Fase 2) ────────
export const hardwareApi = {
  getReaders: (warehouseId?: string) =>
    api.get<{ items: RfidReader[] }>('/hardware/readers', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  createReader: (data: unknown) =>
    api.post<RfidReader>('/hardware/readers', data).then(r => r.data),

  updateReader: (id: string, data: unknown) =>
    api.put<RfidReader>(`/hardware/readers/${id}`, data).then(r => r.data),

  getAntennas: (readerId: string) =>
    api.get<{ items: RfidAntenna[] }>(`/hardware/readers/${readerId}/antennas`).then(r => r.data),

  createAntenna: (readerId: string, data: unknown) =>
    api.post<RfidAntenna>(`/hardware/readers/${readerId}/antennas`, data).then(r => r.data),

  ingestTagRead: (data: unknown) =>
    api.post<RfidTagRead>('/hardware/tag-reads', data).then(r => r.data),

  getTagReads: (params?: Record<string, unknown>) =>
    api.get<PaginatedResponse<RfidTagRead>>('/hardware/tag-reads', { params }).then(r => r.data),

  clearTagReads: (warehouseId?: string) =>
    api.delete<{ deleted: number }>('/hardware/tag-reads', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  getDashboard: (warehouseId?: string) =>
    api.get<RfidDashboardMetrics>('/hardware/dashboard', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    }).then(r => r.data),

  generateZplSscc: (data: unknown) =>
    api.post<ZplLabelResult>('/hardware/labels/zpl/sscc', data).then(r => r.data),
}

// ── ASISTENTE IA AGÉNTICO (Fase 5) ────────────────────
export const aiApi = {
  chat: (message: string, conversationId?: string) =>
    api.post<ChatResponse>('/ai/assistant/chat', {
      message, conversation_id: conversationId,
    }).then(r => r.data),

  getConversations: (params?: Record<string, unknown>) =>
    api.get<ListResponse<AIConversation>>('/ai/assistant/conversations', { params }).then(r => r.data),

  getConversation: (id: string) =>
    api.get<AIConversationDetail>(`/ai/assistant/conversations/${id}`).then(r => r.data),

  transcribe: (audio: Blob) => {
    const form = new FormData()
    form.append('audio', audio, 'audio.webm')
    return api.post<{ text: string }>('/ai/assistant/transcribe', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  speak: (text: string) =>
    api.post('/ai/assistant/speak', { text }, { responseType: 'blob' }).then(r => r.data as Blob),
}
