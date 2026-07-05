import { Navigate, Outlet, createBrowserRouter } from 'react-router-dom';
import { AuthProvider } from '@/hooks/useAuth';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import { LoginPage } from '@/pages/LoginPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { MembersPage } from '@/pages/MembersPage';
import { PageProof } from '@/pages/PageProof';
import { PublicTransparencyPage } from '@/pages/PublicTransparencyPage';
import { PublicTeamsPage } from '@/pages/PublicTeamsPage';

function RootLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}

const legacyDashboardPaths = [
  '/consortium',
  '/members',
  '/pos',
  '/splits',
  '/wallets',
  '/payments',
  '/summary',
];

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/public', element: <PublicTeamsPage /> },
      { path: '/public/:slug', element: <PublicTransparencyPage /> },
      ...legacyDashboardPaths.map((path) => ({ path, element: <Navigate to="/team" replace /> })),
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
          { path: 'settings', element: <SettingsPage /> },
          { path: 'proof/:paymentId', element: <PageProof /> },
        ],
      },
    ],
  },
]);
