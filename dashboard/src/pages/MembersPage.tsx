import { useEffect, useMemo, useRef, useState } from 'react';
import { Users } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/hooks/useAuth';
import { useMembers } from '@/hooks/useMembers';
import { useInvoices } from '@/hooks/useInvoices';
import { useSplits } from '@/hooks/useSplits';
import { TeamMap } from '@/components/team/TeamMap';
import { SplitRulesSection } from '@/components/team/SplitRulesSection';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { PaymentsPanel } from '@/components/payments/PaymentsPanel';
import { cn } from '@/lib/utils';

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

  // Active split rules drive the tabs attached to the top of the graph.
  const activeRules = useMemo(() => (splits ?? []).filter((rule) => rule.active), [splits]);
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);

  // Keep the selected tab on a still-active rule; fall back to the first active
  // rule when the selection is deactivated or removed.
  useEffect(() => {
    if (activeRules.length === 0) {
      if (selectedRuleId !== null) setSelectedRuleId(null);
      return;
    }
    if (!selectedRuleId || !activeRules.some((rule) => rule.id === selectedRuleId)) {
      setSelectedRuleId(activeRules[0].id);
    }
  }, [activeRules, selectedRuleId]);

  const selectedRule = useMemo(
    () => activeRules.find((rule) => rule.id === selectedRuleId) ?? activeRules[0],
    [activeRules, selectedRuleId]
  );

  // Safari-style tabs that attach to the top border of the graph card below.
  const ruleTabs = activeRules.length > 0 ? (
    <div className="os-rule-tabs relative z-10 -mb-px flex gap-1 overflow-x-auto" role="tablist" aria-label="Active split rules">
      {activeRules.map((rule) => {
        const selected = rule.id === selectedRule?.id;
        return (
          <button
            key={rule.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => setSelectedRuleId(rule.id)}
            className={cn(
              'inline-flex shrink-0 items-center gap-2 rounded-t-lg border px-3.5 py-2 text-sm font-medium transition-colors',
              selected
                ? 'border-[#2A2D3A] border-b-transparent bg-[#11121A] text-[#F5F5F7] shadow-[inset_0_2px_0_0_#FF2E93]'
                : 'border-transparent bg-transparent text-[#9AA4B2] hover:bg-white/[0.04] hover:text-[#F5F5F7]'
            )}
          >
            <span className={cn('h-1.5 w-1.5 rounded-full', selected ? 'bg-[#FF2E93]' : 'bg-[#9AA4B2]/50')} />
            <span className="max-w-[160px] truncate">{rule.name}</span>
          </button>
        );
      })}
    </div>
  ) : null;

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
      {activeRules.length === 0 ? (
        <EmptyState
          icon={<Users className="h-8 w-8 text-[#94A3B8]" />}
          message="No active split"
          description="Activate a rule from the library below to map who receives the next Bitcoin payment."
          actionLabel="Create split rule"
          onAction={openSplitRules}
        />
      ) : (
        <TeamMap members={members} workspaceName={workspaceName} selectedRule={selectedRule} tabsSlot={ruleTabs} />
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

      {/* Recent payments — replaces the old "Team partners" table. */}
      <PaymentsPanel />
    </div>
  );
}
