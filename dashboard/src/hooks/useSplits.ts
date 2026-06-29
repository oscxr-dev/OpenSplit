import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import type { SplitRule, SplitRuleCreate, SplitRuleUpdate } from '@/types/api';

export function useSplits() {
  return useQuery<SplitRule[]>({
    queryKey: ['splits'],
    queryFn: async () => {
      const res = await api.get('/splits');
      return res.data;
    },
    staleTime: 1000 * 30,
  });
}

export function useCreateSplit() {
  const queryClient = useQueryClient();

  return useMutation<SplitRule, Error, SplitRuleCreate>({
    mutationFn: async (data) => {
      const res = await api.post('/splits', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['splits'] });
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}

export function useUpdateSplit() {
  const queryClient = useQueryClient();

  return useMutation<SplitRule, Error, { id: string; data: SplitRuleUpdate }>({
    mutationFn: async ({ id, data }) => {
      const res = await api.patch(`/splits/${id}`, data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['splits'] });
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}

export function useActivateSplit() {
  const queryClient = useQueryClient();

  return useMutation<SplitRule, Error, string>({
    mutationFn: async (id) => {
      const res = await api.post(`/splits/${id}/activate`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['splits'] });
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}

export function useDeactivateSplit() {
  const queryClient = useQueryClient();

  return useMutation<SplitRule, Error, string>({
    mutationFn: async (id) => {
      const res = await api.post(`/splits/${id}/deactivate`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['splits'] });
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}

export function useToggleSplitPublic() {
  const queryClient = useQueryClient();

  return useMutation<SplitRule, Error, { id: string; public_enabled: boolean; slug?: string | null }>({
    mutationFn: async ({ id, public_enabled }) => {
      const res = await api.patch(`/splits/${id}/public`, { public_enabled });
      return res.data;
    },
    onSuccess: (_rule, variables) => {
      queryClient.invalidateQueries({ queryKey: ['splits'] });
      queryClient.invalidateQueries({ queryKey: ['public-teams'] });
      if (variables.slug) {
        queryClient.invalidateQueries({ queryKey: ['public-transparency', variables.slug] });
      }
    },
  });
}

export function useDeleteSplit() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      await api.delete(`/splits/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['splits'] });
      queryClient.invalidateQueries({ queryKey: ['members'] });
    },
  });
}
