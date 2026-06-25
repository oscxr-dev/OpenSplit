import { useEffect, useMemo, useRef, useState } from 'react';
import { Users } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/hooks/useAuth';
import { useMembers } from '@/hooks/useMembers';
import { useInvoices } from '@/hooks/useInvoices';
import { useSplits } from '@/hooks/useSplits';
import { TeamMap } from '@/components/team/TeamMap';
import { SplitRulesSection } from '@/components/team/SplitRulesSection';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { formatDateShort, formatSats } from '@/lib/utils';
import { memberPayoutHealth, truncateMiddle } from '@/lib/transparency';

const ACTIVE_PAYOUT_STATUSES = ['pending', 'in_progress'];
const RECENT_PAYMENT_WINDOW_MS = 10 * 60 * 1000;

export function MembersPage() {
  const { tenant } = useAuth();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useMembers();
  const {
    data: splits,
    isLoading: splitsLoading,
    isError: splitsError,
    refetch: refetchSplits,
  } = useSplits();

  // Settled totals (total_paid_sats) only count *completed* splits, which the
  // backend flips from in_progress over time via payout reconciliation. Watch
  // the payments feed so the Team partners section refreshes on its own when a
  // payment is detected or a payout/proof status changes — no manual reload.
  // Light polling runs only while payouts are still settling or recent.
  const paymentInvoices = useInvoices({
    limit: 100,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const active = items.some((invoice) =>
        invoice.splits.some((split) => ACTIVE_PAYOUT_STATUSES.includes(split.status))
      );
      if (active) return 8000;
      const recent = items.some((invoice) => {
        const timestamp = invoice.paid_at || invoice.created_at;
        return !!timestamp && Date.now() - new Date(timestamp).getTime() < RECENT_PAYMENT_WINDOW_MS;
      });
      return recent ? 20000 : false;
    },
  });
  const invoices = useMemo(() => paymentInvoices.data?.items ?? [], [paymentInvoices.data]);

  // Signature of the settled portion of every payment. When it changes (a split
  // reconciled to completed, a retry, or any proof-status change) refetch the
  // members query that feeds the settled totals.
  const settledSignature = useMemo(
    () =>
      invoices
        .map((invoice) => {
          const completed = invoice.splits.filter((split) => split.status === 'completed');
          const settledSats = completed.reduce((sum, split) => sum + split.amount_sats, 0);
          return `${invoice.id}:${completed.length}:${settledSats}`;
        })
        .join('|'),
    [invoices]
  );
  const previousSignature = useRef<string | null>(null);
  useEffect(() => {
    if (previousSignature.current !== null && previousSignature.current !== settledSignature) {
      queryClient.invalidateQueries({ queryKey: ['members'] });
    }
    previousSignature.current = settledSignature;
  }, [settledSignature, queryClient]);

  const splitSectionRef = useRef<HTMLDivElement | null>(null);
  const [splitEditorKey, setSplitEditorKey] = useState(0);

  const members = useMemo(
    () => (data ?? []).filter((member) => (member.current_percentage ?? 0) > 0),
    [data]
  );
  const workspaceName = tenant?.tenant.brand_display_name || tenant?.tenant.name || 'OpenSplit';
  const failedCount = members.reduce((sum, member) => sum + member.failed_count, 0);

  function openSplitRules() {
    setSplitEditorKey((value) => value + 1);
    window.setTimeout(() => {
      splitSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-80" />
        <Skeleton className="h-[620px] w-full" />
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Could not load team members" onRetry={() => refetch()} />;
  }

  return (
    <div className="space-y-8">
      {!members.length ? (
        <EmptyState
          icon={<Users className="h-8 w-8 text-[#94A3B8]" />}
          message="No partners yet"
          description="Create a split rule to define who receives the next Bitcoin payment."
          actionLabel="Create split rule"
          onAction={openSplitRules}
        />
      ) : (
        <TeamMap members={members} workspaceName={workspaceName} />
      )}

      <div ref={splitSectionRef}>
        <SplitRulesSection
          key={splitEditorKey}
          splits={splits}
          isLoading={splitsLoading}
          isError={splitsError}
          onRetry={() => refetchSplits()}
          startOpen={splitEditorKey > 0}
        />
      </div>

      {!!members.length && (
        <Card className="bg-[#11131F]/48 shadow-none">
          <CardContent className="p-0">
            <div className="flex items-center justify-between border-b border-white/[0.07] p-5">
              <div className="flex items-center gap-3">
                <Users className="h-5 w-5 text-[#94A3B8]" strokeWidth={1.8} />
                <div>
                  <h2 className="font-semibold text-[#F5F5F7]">Team partners</h2>
                  <p className="mt-1 text-sm text-[#94A3B8]">
                    {members.length} partners · {failedCount} payouts need attention
                  </p>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b border-white/[0.06] text-xs uppercase tracking-[0.12em] text-[#94A3B8]">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Partner</th>
                    <th className="px-5 py-3 font-semibold">npub</th>
                    <th className="px-5 py-3 font-semibold">Share</th>
                    <th className="px-5 py-3 font-semibold">Settled</th>
                    <th className="px-5 py-3 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06]">
                  {members.map((member, index) => {
                    const health = memberPayoutHealth(member.failed_count);
                    return (
                      <tr key={`${member.label}-${member.nostr_pubkey ?? member.ln_address ?? index}`} className="transition hover:bg-white/[0.025]">
                        <td className="px-5 py-4">
                          <p className="font-medium text-[#F5F5F7]">{member.label}</p>
                          <p className="mt-1 text-xs text-[#94A3B8]">
                            {member.payment_count} splits · last {formatDateShort(member.last_payment_at)}
                            {member.collision && ' · identity overlap'}
                          </p>
                        </td>
                        <td className="px-5 py-4">
                          <span className="font-mono text-xs text-[#94A3B8]">
                            {member.nostr_pubkey ? truncateMiddle(member.nostr_pubkey) : 'not published'}
                          </span>
                        </td>
                        <td className="px-5 py-4 font-mono font-semibold text-[#F5F5F7]">
                          {member.current_percentage != null ? `${member.current_percentage}%` : '—'}
                        </td>
                        <td className="px-5 py-4 font-mono text-[#94A3B8]">{formatSats(member.total_paid_sats)}</td>
                        <td className="px-5 py-4">
                          <Badge variant={health === 'failed' ? 'error' : 'success'}>
                            {health === 'failed' ? 'Needs retry' : 'Active'}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
