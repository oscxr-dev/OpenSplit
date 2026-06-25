import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { setTokens, clearTokens, isAuthenticated } from '@/lib/auth';
import api from '@/lib/api';
import type { TenantHealth } from '@/types/api';

interface AuthContextValue {
  isAuth: boolean;
  tenant: TenantHealth | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshTenant: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuth, setIsAuth] = useState<boolean>(isAuthenticated());
  const [tenant, setTenant] = useState<TenantHealth | null>(null);

  const refreshTenant = useCallback(async () => {
    if (!isAuthenticated()) return;
    try {
      const res = await api.get('/tenants/me');
      setTenant(res.data);
    } catch {
      // Silently fail
    }
  }, []);

  useEffect(() => {
    if (isAuth) {
      refreshTenant();
    }
  }, [isAuth, refreshTenant]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post('/auth/login', { email, password });
    const { access_token, refresh_token } = res.data;
    setTokens(access_token, refresh_token);
    setIsAuth(true);
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setIsAuth(false);
    setTenant(null);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuth, tenant, login, logout, refreshTenant }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
