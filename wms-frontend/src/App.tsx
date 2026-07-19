import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'

import { useAuthStore } from '@/store/authStore'
import { AppLayout } from '@/components/layout/AppLayout'
import { LoginPage } from '@/pages/auth/LoginPage'
import { DashboardPage } from '@/pages/dashboard/DashboardPage'
// Inventory
import { StockPage } from '@/pages/inventory/StockPage'
import { MovementsPage } from '@/pages/inventory/MovementsPage'
import { AdjustmentsPage } from '@/pages/inventory/AdjustmentsPage'
import { ExpiryPage } from '@/pages/inventory/ExpiryPage'
import { CycleCountsPage } from '@/pages/inventory/CycleCountsPage'
import { TransfersPage } from '@/pages/inventory/TransfersPage'
// Inbound
import { POListPage } from '@/pages/inbound/POListPage'
import { GRNListPage } from '@/pages/inbound/GRNListPage'
import { QualityPage } from '@/pages/inbound/QualityPage'
import { PutawayPage } from '@/pages/inbound/PutawayPage'
import { RTVListPage } from '@/pages/inbound/RTVListPage'
// Outbound
import { SOListPage } from '@/pages/outbound/SOListPage'
import { WavesPage } from '@/pages/outbound/WavesPage'
import { PickingPage } from '@/pages/outbound/PickingPage'
import { PackingPage } from '@/pages/outbound/PackingPage'
import { ShipmentsPage } from '@/pages/outbound/ShipmentsPage'
import { ReturnsPage } from '@/pages/outbound/ReturnsPage'
import { StreamingPage } from '@/pages/outbound/StreamingPage'
// Master Data
import { MasterDataPage } from '@/pages/master/MasterDataPage'
// Labor & Slotting
import { LaborPage } from '@/pages/labor/LaborPage'
import { SlottingPage } from '@/pages/slotting/SlottingPage'
// Hardware RFID
import { RfidTestPage } from '@/pages/hardware/RfidTestPage'
// Asistente IA
import { AssistantPage } from '@/pages/ai/AssistantPage'
// Settings
import { SettingsPage } from '@/pages/settings/SettingsPage'

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function GuestOnly({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  return isAuthenticated ? <Navigate to="/" replace /> : <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
      <BrowserRouter>
        <Routes>
          {/* Auth */}
          <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />

          {/* App */}
          <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
            <Route index element={<DashboardPage />} />

            {/* Inventory */}
            <Route path="inventory">
              <Route path="stock" element={<StockPage />} />
              <Route path="movements" element={<MovementsPage />} />
              <Route path="adjustments" element={<AdjustmentsPage />} />
              <Route path="expiry" element={<ExpiryPage />} />
              <Route path="cycle-counts" element={<CycleCountsPage />} />
              <Route path="transfers" element={<TransfersPage />} />
            </Route>

            {/* Inbound */}
            <Route path="inbound">
              <Route path="pos" element={<POListPage />} />
              <Route path="grns" element={<GRNListPage />} />
              <Route path="quality" element={<QualityPage />} />
              <Route path="putaway" element={<PutawayPage />} />
              <Route path="rtv" element={<RTVListPage />} />
            </Route>

            {/* Outbound */}
            <Route path="outbound">
              <Route path="orders" element={<SOListPage />} />
              <Route path="waves" element={<WavesPage />} />
              <Route path="picking" element={<PickingPage />} />
              <Route path="packing" element={<PackingPage />} />
              <Route path="shipments" element={<ShipmentsPage />} />
              <Route path="returns" element={<ReturnsPage />} />
              <Route path="streaming" element={<StreamingPage />} />
            </Route>

            {/* Master Data */}
            <Route path="master">
              <Route path="products" element={<MasterDataPage />} />
              <Route path="suppliers" element={<MasterDataPage />} />
              <Route path="customers" element={<MasterDataPage />} />
              <Route path="box-types" element={<MasterDataPage />} />
              <Route path="locations" element={<MasterDataPage />} />
            </Route>

            {/* Labor & Slotting */}
            <Route path="labor" element={<LaborPage />} />
            <Route path="slotting" element={<SlottingPage />} />

            {/* Hardware RFID */}
            <Route path="hardware/rfid" element={<RfidTestPage />} />

            {/* Asistente IA */}
            <Route path="ai/assistant" element={<AssistantPage />} />

            {/* Settings */}
            <Route path="settings" element={<SettingsPage />} />

            {/* 404 */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
