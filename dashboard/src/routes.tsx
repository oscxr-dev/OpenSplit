import { Navigate, Outlet, createBrowserRouter } from 'react-router-dom';
import { AuthProvider } from '@/hooks/useAuth';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import { LoginPage } from '@/pages/LoginPage';
import { PosPage } from '@/pages/PosPage';
import { WalletsPage } from '@/pages/WalletsPage';
import { PaymentsPage } from '@/pages/PaymentsPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { MembersPage } from '@/pages/MembersPage';
import { PublicTransparencyPage } from '@/pages/PublicTransparencyPage';

function RootLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/public/:slug', element: <PublicTransparencyPage /> },
      {
        path: '/',
        element: (
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        ),
        children: [
          { index: true, element: <Navigate to="/team" replace /> },
          { path: 'team', element: <MembersPage /> },
          { path: 'consortium', element: <Navigate to="/team" replace /> },
          { path: 'members', element: <Navigate to="/team" replace /> },
          { path: 'pos', element: <PosPage /> },
          { path: 'splits', element: <Navigate to="/team" replace /> },
          { path: 'wallets', element: <WalletsPage /> },
          { path: 'payments', element: <PaymentsPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
]);
