import { AlertCircle, CheckCircle, Clock, Copy, ExternalLink, ReceiptText, RotateCcw, ShieldCheck } from 'lucide-react';
import { useProof } from '@/hooks/useProof';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { cn, formatDate, formatSats, payoutStatusLabel } from '@/lib/utils';
import { btcpayPayoutsUrl, isWaitingInBtcpay, WAITING_IN_BTCPAY_HINT } from '@/lib/payments';
import { proofBalanceLabel, truncateMiddle } from '@/lib/transparency';
import type { Invoice, PaymentSplit } from '@/types/api';

interface SplitProofReceiptProps {
  payment: Invoice;
  onRetrySplit?: (split: PaymentSplit) => void;
  retrying?: boolean;
}

export function SplitProofReceipt({ payment, onRetrySplit, retrying = false }: SplitProofReceiptProps) {
  const { data: proof, isLoading, isError, refetch } = useProof(payment.id);
  const { tenant } = useAuth();
  const payoutsUrl = btcpayPayoutsUrl(
    tenant?.tenant.btcpay_url,
    tenant?.tenant.btcpay_store_id,
    window.location.hostname
  );

  const proofRows = proof?.members.map((member) => {
    const matchingSplit = payment.splits.find((split) => split.id === member.split_id);
    return {
      id: member.split_id,
      label: member.label || matchingSplit?.label || 'Unnamed partner',
      identity: member.nostr_pubkey || matchingSplit?.ln_address || member.ln_address,
      percentage: member.percentage,
      amountSats: member.amount_sats,
      status: member.payout_status,
      rawState: member.btcpay_payout_state ?? matchingSplit?.btcpay_payout_state ?? null,
      retrySplit: matchingSplit,
    };
  }) ?? payment.splits.map((split) => ({
    id: split.id,
    label: split.label || 'Unnamed partner',
    identity: split.ln_address,
    percentage: null,
    amountSats: split.amount_sats,
    status: split.status,
    rawState: split.btcpay_payout_state ?? null,
    retrySplit: split,
  }));

  return (
    <article className="split-proof-receipt overflow-hidden rounded-lg border border-[#FF2D78]/18 bg-[#11131F]">
      <header className="border-b border-white/[0.08] bg-white/[0.025] p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
              <h2 className="text-xl font-semibold text-[#F5F5F7]">Split Proof</h2>
            </div>
            <p className="mt-2 text-sm text-[#94A3B8]">A sealed receipt showing how this invoice was divided.</p>
          </div>
          <p className="font-mono text-xs font-semibold text-[#FF2D78]">
            {proof ? proofBalanceLabel(proof.integrity.balanced) : 'loading proof'}
          </p>
        </div>
      </header>

      <div className="grid gap-4 p-5 sm:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-[#94A3B8]">Amount</p>
          <p className="mt-2 font-mono text-2xl font-semibold text-[#F5F5F7]">{formatSats(payment.amount_sats)}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-[#94A3B8]">Rule</p>
          <p className="mt-2 font-mono text-lg font-semibold text-[#F5F5F7]">
            {proof?.split_rule_version != null ? `v${proof.split_rule_version} sealed` : 'pending'}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-[#94A3B8]">Paid</p>
          <p className="mt-2 font-mono text-sm text-[#F5F5F7]">{formatDate(payment.paid_at || payment.created_at)}</p>
        </div>
      </div>

      <div className="border-y border-white/[0.08] px-5 py-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#F5F5F7]">
          <ReceiptText className="h-4 w-4 text-[#FF2D78]" strokeWidth={1.8} />
          Team shares
        </div>

        {isLoading && <Skeleton className="mt-4 h-28 w-full" />}

        {isError && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-red-300/15 bg-red-400/[0.08] p-3 text-sm text-red-300">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" strokeWidth={1.8} />
              Could not load proof.
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        )}

        <div className="mt-4 space-y-2">
          {proofRows.map((row) => {
            const waiting = isWaitingInBtcpay({ status: row.status, btcpay_payout_state: row.rawState });
            return (
              <div key={row.id} className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3">
                <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
                  <div className="min-w-0">
                    <p className="font-medium text-[#F5F5F7]">{row.label}</p>
                    <p className="mt-1 truncate font-mono text-xs text-[#94A3B8]">
                      {row.identity ? truncateMiddle(row.identity) : 'no public identity'}
                    </p>
                  </div>
                  <p className="font-mono text-sm font-semibold text-[#F5F5F7]">
                    {row.percentage != null ? `${row.percentage}%` : '—'}
                  </p>
                  <div className="flex items-center justify-between gap-3 sm:justify-end">
                    <div className="text-right">
                      <p className="font-mono text-sm font-semibold text-[#F5F5F7]">{formatSats(row.amountSats)}</p>
                      <p className={cn('mt-1 text-xs', waiting ? 'text-amber-200' : 'text-[#94A3B8]')}>
                        {waiting ? 'Waiting in BTCPay' : payoutStatusLabel(row.status)}
                      </p>
                    </div>
                    {row.status === 'failed' && row.retrySplit && onRetrySplit && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        loading={retrying}
                        onClick={() => onRetrySplit(row.retrySplit!)}
                        aria-label={`Retry payout for ${row.label}`}
                      >
                        <RotateCcw className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>

                {waiting && (
                  <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 rounded border border-amber-300/15 bg-amber-400/[0.08] px-2.5 py-1.5 text-xs text-amber-200">
                    <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
                    <span>{WAITING_IN_BTCPAY_HINT}.</span>
                    {payoutsUrl && (
                      <a
                        href={payoutsUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-medium underline underline-offset-2 hover:text-amber-100"
                      >
                        Open in BTCPay
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <footer className="space-y-3 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#F5F5F7]">
          <CheckCircle className="h-4 w-4 text-[#FF2D78]" strokeWidth={1.8} />
          Proof integrity
        </div>
        <div className="grid gap-3 text-xs sm:grid-cols-2">
          <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3">
            <p className="text-[#94A3B8]">Payment ID</p>
            <p className="mt-1 truncate font-mono text-[#F5F5F7]">{payment.id}</p>
          </div>
          <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3">
            <p className="text-[#94A3B8]">Proof source</p>
            <p className="mt-1 font-mono text-[#F5F5F7]">/payments/{payment.id}/proof</p>
          </div>
          <div className="rounded-md border border-white/[0.07] bg-[#0A0B12]/42 p-3 sm:col-span-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[#94A3B8]">Balance</p>
              <Copy className="h-3.5 w-3.5 text-[#94A3B8]" strokeWidth={1.8} />
            </div>
            <p className="mt-1 font-mono text-[#F5F5F7]">
              {proof
                ? `${formatSats(proof.integrity.split_sum_sats)} / ${formatSats(proof.integrity.payment_amount_sats)}`
                : 'waiting for proof'}
            </p>
          </div>
        </div>
      </footer>
    </article>
  );
}
