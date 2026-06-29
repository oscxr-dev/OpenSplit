import { useQuery } from '@tanstack/react-query';
import publicApi from '@/lib/publicApi';
import type { PublicTeamSummary } from '@/types/api';

interface PublicTeamsResponse {
  teams: PublicTeamSummary[];
}

// Unauthenticated discovery list of opt-in public teams (privacy-safe metadata).
export function usePublicTeams() {
  return useQuery<PublicTeamSummary[]>({
    queryKey: ['public-teams'],
    queryFn: async () => {
      const res = await publicApi.get<PublicTeamsResponse>('/public-teams');
      return res.data.teams ?? [];
    },
    retry: false,
    staleTime: 1000 * 60,
  });
}
