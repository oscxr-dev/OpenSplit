import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import api from '@/lib/api';
import type { Invoice, InvoiceCreateRequest, InvoiceListResponse } from '@/types/api';

interface UseInvoicesOptions {
  status?: string;
  search?: string;
  offset?: number;
  limit?: number;
  enabled?: boolean;
  /** Poll interval in ms, false to disable, or a function of the query for
   *  dynamic polling. Used to catch payout reconciliation that happens on the
   *  backend over time. */
  refetchInterval?: UseQueryOptions<InvoiceListResponse>['refetchInterval'];
}

export function useInvoices(options: UseInvoicesOptions = {}) {
  const { status, search, offset = 0, limit = 50, refetchInterval = false } = options;

  return useQuery<InvoiceListResponse>({
    queryKey: ['payments', { status, search, offset, limit }],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      if (search) params.set('search', search);
      params.set('offset', offset.toString());
      params.set('limit', limit.toString());
      const res = await api.get(`/payments?${params.toString()}`);
      return res.data;
    },
    staleTime: 1000 * 15,
    refetchInterval,
  });
}

export function useInvoice(id: string) {
  return useQuery<Invoice>({
    queryKey: ['invoice', id],
    queryFn: async () => {
      const res = await api.get(`/payments/${id}`);
      return res.data;
    },
    enabled: !!id,
    refetchInterval: false,
  });
}

export function useRetryPaymentSplit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ paymentId, splitId }: { paymentId: string; splitId: string }) => {
      const response = await api.post(`/payments/${paymentId}/splits/${splitId}/retry`);
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['payments'] });
      queryClient.invalidateQueries({ queryKey: ['invoice', variables.paymentId] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      // Retrying a payout changes its split (proof) status, which feeds the
      // Team partners settled totals.
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}

export function useCreateInvoice() {
  const queryClient = useQueryClient();

  return useMutation<Invoice, Error, InvoiceCreateRequest>({
    mutationFn: async (data) => {
      const res = await api.post('/invoices', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payments'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}
