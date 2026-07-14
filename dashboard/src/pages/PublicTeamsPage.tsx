import { useMemo, useState } from 'react';
import { Layers, Sparkles, Users } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { TopBar } from '@/components/layout/TopBar';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/shared/ErrorState';
import { PublicTeamsMap } from '@/components/public/PublicTeamsMap';
import { PublicTeamSearch, type PublicTeamSort } from '@/components/public/PublicTeamSearch';
import { PublicTeamsLeaderboard } from '@/components/public/PublicTeamsLeaderboard';
import { usePublicTeams } from '@/hooks/usePublicTeams';
import type { PublicTeamSummary } from '@/types/api';

const RECENTLY_ACTIVE_MS = 7 * 24 * 60 * 60 * 1000;

function sortTeams(teams: PublicTeamSummary[], sort: PublicTeamSort): PublicTeamSummary[] {
  const copy = [...teams];
  if (sort === 'active') {
    copy.sort((a, b) => (Date.parse(b.last_activity ?? '') || 0) - (Date.parse(a.last_activity ?? '') || 0));
  } else if (sort === 'newest') {
    copy.sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0));
  } else {
    copy.sort((a, b) => b.completed_splits - a.completed_splits);
  }
  return copy;
}

function StatCard({ label, value, icon: Icon }: { label: string; value: number; icon: LucideIcon }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3.5">
      <div className="flex items-center justify-between">
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[#94A3B8]">{label}</p>
        <div className="rounded-lg border border-[#FF2D78]/15 bg-[#FF2D78]/10 p-1.5 text-[#FF2D78]">
          <Icon className="h-3.5 w-3.5" strokeWidth={1.8} />
        </div>
      </div>
      <p className="mt-2 text-2xl font-bold tracking-tight text-[#F5F5F7]">{value}</p>
    </div>
  );
}

export function PublicTeamsPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = usePublicTeams();
  const teams = useMemo(() => data ?? [], [data]);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<PublicTeamSort>('splits');

  const stats = useMemo(() => {
    const now = Date.now();
    return {
      teamCount: teams.length,
      publicSplits: teams.reduce((sum, team) => sum + team.completed_splits, 0),
      recentlyActive: teams.filter(
        (team) => team.last_activity && now - Date.parse(team.last_activity) < RECENTLY_ACTIVE_MS
      ).length,
    };
  }, [teams]);

  const visibleTeams = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? teams.filter((team) => team.name.toLowerCase().includes(q) || team.slug.includes(q))
      : teams;
    return sortTeams(filtered, sort);
  }, [teams, query, sort]);

  return (
    <div className="opensplit-app min-h-screen pt-20 text-[#F5F5F7] lg:pt-[68px]">
      <TopBar />

      <main className="mx-auto max-w-6xl space-y-5 px-4 pb-32 pt-3 sm:px-6 sm:pt-4 md:pb-8 lg:px-8">
        {/* Small stats — activity metadata only, never money volume. */}
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard label={t('public.stats.publicTeams')} value={stats.teamCount} icon={Users} />
          <StatCard label={t('public.stats.publicSplits')} value={stats.publicSplits} icon={Layers} />
          <StatCard label={t('public.stats.recentlyActive')} value={stats.recentlyActive} icon={Sparkles} />
        </div>

        {isLoading ? (
          <div className="space-y-6">
            <Skeleton className="h-[420px] w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : isError ? (
          <ErrorState message={t('public.loadError')} onRetry={() => refetch()} />
        ) : (
          <>
            {/* World map */}
            <PublicTeamsMap teams={teams} />

            {/* Team list */}
            <section className="space-y-4">
              <PublicTeamSearch query={query} onQueryChange={setQuery} sort={sort} onSortChange={setSort} />
              <PublicTeamsLeaderboard teams={visibleTeams} />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
