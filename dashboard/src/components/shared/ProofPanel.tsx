import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronUp, ShieldCheck, XCircle } from 'lucide-react';
import { useProof } from '@/hooks/useProof';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { cn, formatSats, payoutStatusLabel } from '@/lib/utils';
import { proofBalanceLabel, truncateMiddle } from '@/lib/transparency';

/**
 * Proof of how one payment was split, backed by GET /payments/{id}/proof.
 * Fetches lazily — only once the operator expands the panel.
 */
export function ProofPanel({ paymentId }: { paymentId: string }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useProof(open ? paymentId : null);

  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-white/85">
          <ShieldCheck className="h-4 w-4 text-violet-300" strokeWidth={1.8} />
          Split proof
        </span>
        {open ? (
          <ChevronUp className="h-4 w-4 text-white/40" />
        ) : (
          <ChevronDown className="h-4 w-4 text-white/40" />
        )}
      </button>

      {open && (
        <div className="border-t border-white/[0.07] p-4">
          {isLoading && <Skeleton className="h-32 w-full" />}

          {isError && (
            <div className="flex items-center justify-between gap-3 text-sm text-red-300">
              <span>Could not load proof.</span>
              <button
                type="button"
                onClick={() => refetch()}
                className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-semibold text-white/70 hover:bg-white/[0.06]"
              >
                Retry
              </button>
            </div>
          )}

          {data && (
            <div className="space-y-4">
              <div
                className={cn(
                  'flex items-center justify-between gap-3 rounded-xl border px-4 py-3',
                  data.integrity.balanced
                    ? 'border-emerald-300/15 bg-emerald-400/[0.08]'
                    : 'border-red-300/15 bg-red-400/[0.08]'
                )}
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-white/90">
                  {data.integrity.balanced ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-300" strokeWidth={1.8} />
                  ) : (
                    <XCircle className="h-4 w-4 text-red-300" strokeWidth={1.8} />
                  )}
                  {proofBalanceLabel(data.integrity.balanced)}
                </span>
                <span className="font-mono text-xs text-white/55">
                  {formatSats(data.integrity.split_sum_sats)} / {formatSats(data.integrity.payment_amount_sats)}
                  {data.integrity.difference_sats !== 0 &&
                    ` · Δ ${formatSats(data.integrity.difference_sats)}`}
                </span>
              </div>

              <p className="text-xs text-white/40">
                Split rule
                {data.split_rule_version != null ? ` · version ${data.split_rule_version}` : ''} ·{' '}
                {data.members.length} destinations
              </p>

              <div className="space-y-2">
                {data.members.map((split) => (
                  <div
                    key={split.split_id}
                    className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-white/90">
                        {split.label || 'Unlabeled'}
                        {split.percentage != null && (
                          <span className="ml-2 font-mono text-xs text-white/45">{split.percentage}%</span>
                        )}
                      </p>
                      {split.nostr_pubkey && (
                        <p className="mt-1 truncate font-mono text-[11px] text-white/35">
                          {truncateMiddle(split.nostr_pubkey)}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="font-mono text-sm text-white/80">{formatSats(split.amount_sats)}</span>
                      <Badge>{payoutStatusLabel(split.payout_status)}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
