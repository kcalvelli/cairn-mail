/**
 * App - Main application component with routing and providers
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { get, set, del } from 'idb-keyval';
import { ThemeProvider } from './contexts/ThemeContext';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { MessageDetailPage } from './pages/MessageDetailPage';
import { AccountsPage } from './pages/AccountsPage';
import { SettingsPage } from './pages/SettingsPage';
import { StatsPage } from './pages/StatsPage';
import Compose from './pages/Compose';
import DraftsPage from './pages/DraftsPage';
import { ToastContainer } from './components/ToastContainer';
import { TokenGate } from './components/TokenGate';
import { useWebSocket } from './hooks/useWebSocket';

declare const __APP_VERSION__: string;

// Create React Query client with cache persistence settings
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 1000 * 60 * 60 * 24 * 7, // 7 days - keep cache for offline use
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Create IndexedDB persister for offline cache
const persister = {
  persistClient: async (client: any) => {
    await set('react-query-cache', client);
  },
  restoreClient: async () => {
    return await get('react-query-cache');
  },
  removeClient: async () => {
    await del('react-query-cache');
  },
};

function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: 1000 * 60 * 60 * 24 * 7, // 7 days
        buster: __APP_VERSION__, // Invalidates cache on new deploy
      }}
    >
      <ThemeProvider>
        <BrowserRouter>
          <AppContent />
        </BrowserRouter>
      </ThemeProvider>
    </PersistQueryClientProvider>
  );
}

function AppContent() {
  // Initialize WebSocket connection for real-time updates
  useWebSocket();

  return (
    <>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="messages" element={<DashboardPage />} />
          <Route path="messages/:id" element={<MessageDetailPage />} />
          <Route path="compose" element={<Compose />} />
          <Route path="drafts" element={<DraftsPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      <ToastContainer />
      <TokenGate />
    </>
  );
}

export default App;
