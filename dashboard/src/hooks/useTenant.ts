import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { TenantHealth } from '@/types/api';

export function useTenant() {
  return useQuery<TenantHealth>({
    queryKey: ['tenant'],
    queryFn: async () => {
      const res = await api.get('/tenants/me');
      return res.data;
    },
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });
}
