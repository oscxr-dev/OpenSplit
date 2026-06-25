import { useQuery } from '@tanstack/react-query';
import publicApi from '@/lib/publicApi';
import type { PublicTransparency } from '@/types/api';

// Uses the no-auth client: this runs on the unauthenticated public page.
export function usePublicTransparency(slug: string | undefined) {
  return useQuery<PublicTransparency>({
    queryKey: ['public-transparency', slug],
    queryFn: async () => {
      const res = await publicApi.get(`/public/${slug}`);
      return res.data;
    },
    enabled: !!slug,
    retry: false,
    staleTime: 1000 * 60,
  });
}
