import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import type { NostrProof, SplitProof } from '@/types/api';

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

/** Sign a paid payment's proof with the team's Nostr key (server-side env
 *  key). Idempotent on the backend; on success the proof query is refreshed
 *  so the receipt shows the signed event. */
export function useSignProof(paymentId: string) {
  const queryClient = useQueryClient();
  return useMutation<NostrProof>({
    mutationFn: async () => {
      const res = await api.post(`/payments/${paymentId}/proof/sign`);
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['proof', paymentId] });
    },
  });
}

/** (Re-)publish an already-signed proof to the server's configured Nostr
 *  relays. Best-effort on the backend: relay failures come back as per-relay
 *  results, not HTTP errors. Refreshes the proof so the receipt shows them. */
export function usePublishProof(paymentId: string) {
  const queryClient = useQueryClient();
  return useMutation<NostrProof>({
    mutationFn: async () => {
      const res = await api.post(`/payments/${paymentId}/proof/publish`);
      return res.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['proof', paymentId] });
    },
  });
}
