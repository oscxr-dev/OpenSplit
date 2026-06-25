import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { SplitProof } from '@/types/api';

export function useProof(paymentId: string | null) {
  return useQuery<SplitProof>({
    queryKey: ['proof', paymentId],
    queryFn: async () => {
      const res = await api.get(`/payments/${paymentId}/proof`);
      return res.data;
    },
    enabled: !!paymentId,
    staleTime: 1000 * 30,
  });
}
