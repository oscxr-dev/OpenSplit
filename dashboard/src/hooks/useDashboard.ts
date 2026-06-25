import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { DashboardSummary } from '@/types/api';

export function useDashboardSummary() {
  return useQuery<DashboardSummary>({
    queryKey: ['dashboard-summary'],
    queryFn: async () => {
      const response = await api.get('/dashboard/summary');
      return response.data;
    },
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}
