import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { TenantStatus } from '@/types/api';

/** Aggregate pipeline health for the Team page status strip. Polls every ~30s
 *  so the strip walks green on its own as the operator fixes each step. */
export function useTenantStatus() {
  return useQuery<TenantStatus>({
    queryKey: ['tenant-status'],
    queryFn: async () => {
      const res = await api.get('/tenants/me/status');
      return res.data;
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
