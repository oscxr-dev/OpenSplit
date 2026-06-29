import { ArrowUpRight, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { EmptyState } from '@/components/shared/EmptyState';
import { relativeTime } from '@/lib/time';
import type { PublicTeamSummary } from '@/types/api';

function locationLabel(team: PublicTeamSummary): string | null {
  if (!team.country) return null;
  return team.city ? `${team.city}, ${team.country}` : team.country;
}

export function PublicTeamsLeaderboard({ teams }: { teams: PublicTeamSummary[] }) {
  if (teams.length === 0) {
    return (
      <EmptyState
        icon={<Users className="h-7 w-7" />}
        message="No public teams match your search"
        description="Try a different name, or check back as more teams turn their public proof page on."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.08]">
      <div className="divide-y divide-white/[0.06]">
        {teams.map((team) => {
          const location = locationLabel(team);
          return (
            <div key={team.slug} className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:gap-5 sm:px-5">
              <div className="min-w-0 sm:flex-1">
                <p className="truncate font-medium text-[#F5F5F7]">{team.name}</p>
                <p className="mt-0.5 truncate font-mono text-xs text-[#94A3B8]">
                  /public/{team.slug}
                  {location && <span> · {location}</span>}
                </p>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-4 sm:justify-end">
                <div className="text-right">
                  <p className="font-semibold tabular-nums text-[#F5F5F7]">{team.completed_splits}</p>
                  <p className="text-[11px] text-[#94A3B8]">splits</p>
                </div>
                <div className="hidden text-right sm:block">
                  <p className="text-xs text-[#94A3B8]">{relativeTime(team.last_activity)}</p>
                  <p className="text-[11px] text-[#94A3B8]">last activity</p>
                </div>
                <Link
                  to={`/public/${team.slug}`}
                  className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg border border-white/[0.10] bg-white/[0.04] px-3 text-sm font-medium text-[#F5F5F7] transition-colors hover:border-[#FF2D78]/40 hover:bg-[#FF2D78]/[0.08]"
                >
                  View proof
                  <ArrowUpRight className="h-4 w-4 text-[#FF2D78]" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
