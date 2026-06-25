import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { Member } from '@/types/api';

export function useMembers() {
  return useQuery<Member[]>({
    queryKey: ['members'],
    queryFn: async () => {
      const res = await api.get('/members');
      return res.data;
    },
    staleTime: 1000 * 30,
  });
}
