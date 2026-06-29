import { useMemo, useState } from 'react';
import { ReceiptText } from 'lucide-react';
import { toast } from 'sonner';
import { useInvoices, useRetryPaymentSplit } from '@/hooks/useInvoices';
import { SplitProofReceipt } from '@/components/payments/SplitProofReceipt';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { cn, formatDateShort, formatFiat, formatSats, payoutStatusLabel } from '@/lib/utils';
import { completedSummary, isDemoHistoryPayment, paymentPayoutStatus } from '@/lib/payments';
import type { Invoice, PaymentSplit } from '@/types/api';

const COUNT_OPTIONS = [5, 10, 15, 21] as const;
const DEFAULT_COUNT = 5;
// Fetch a fixed page once (shares the cache with the Team page's invoice query)
// and slice client-side, so the count selector is instant with no refetch.
const FETCH_LIMIT = 100;

/**
 * Compact recent-transactions panel — reuses the same invoices hook, payment
 * helpers and split-proof dialog as the full Payments page. Shows the latest
 * live transactions with a 5 / 10 / 15 / 21 count selector (default 5).
 */
export function PaymentsPanel() {
  const [count, setCount] = useState<number>(DEFAULT_COUNT);
  const [selectedPayment, setSelectedPayment] = useState<Invoice | null>(null);
  const retrySplit = useRetryPaymentSplit();

  const { data, isLoading, isError, refetch } = useInvoices({ limit: FETCH_LIMIT });

  const livePayments = useMemo(
    () => (data?.items ?? []).filter((payment) => !isDemoHistoryPayment(payment)),
    [data]
  );
  const visiblePayments = useMemo(() => livePayments.slice(0, count), [livePayments, count]);

  async function handleRetry(split: PaymentSplit) {
    if (!selectedPayment) return;
    const confirmed = window.confirm(
      `Retry ${formatSats(split.amount_sats)} payout to ${split.label || 'this partner'}?`
    );
    if (!confirmed) return;

    try {
      const updated = await retrySplit.mutateAsync({ paymentId: selectedPayment.id, splitId: split.id });
      setSelectedPayment({
        ...selectedPayment,
        splits: selectedPayment.splits.map((item) => (item.id === split.id ? updated : item)),
      });
      toast.success('Payout retry started.');
    } catch {
      toast.error('Could not retry payout.');
    }
  }

  return (
    <Card className="bg-[#11131F]/48 shadow-none">
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] p-5">
          <div className="flex items-center gap-3">
            <div className="rounded-lg border border-[#FF2E93]/15 bg-[#FF2E93]/10 p-2 text-[#FF2E93]">
              <ReceiptText className="h-4 w-4" strokeWidth={1.8} />
            </div>
            <div>
              <h2 className="font-semibold text-[#F5F5F7]">Recent payments</h2>
              <p className="mt-1 text-sm text-[#94A3B8]">Latest transactions and their split proof status</p>
            </div>
          </div>

          {/* Count selector: 5 / 10 / 15 / 21 (default 5) — slices client-side. */}
          <div
            className="flex items-center gap-0.5 rounded-lg border border-white/[0.08] bg-white/[0.03] p-0.5"
            role="group"
            aria-label="Number of transactions to show"
          >
            {COUNT_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={count === option}
                onClick={() => setCount(option)}
                className={cn(
                  'min-w-8 rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                  count === option
                    ? 'bg-[#FF2E93]/15 text-[#F5F5F7]'
                    : 'text-[#94A3B8] hover:text-[#F5F5F7]'
                )}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : isError ? (
          <div className="p-5">
            <ErrorState message="Could not load payments" onRetry={() => refetch()} />
          </div>
        ) : visiblePayments.length === 0 ? (
          <EmptyState
            className="min-h-0 rounded-none border-0 bg-transparent py-12"
            icon={<ReceiptText className="h-7 w-7" />}
            message="No payments yet"
            description="Paid invoices will appear here as soon as your first split settles."
          />
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {visiblePayments.map((payment) => {
              const status = paymentPayoutStatus(payment);
              const fiat = formatFiat(payment.fiat_amount, payment.fiat_currency);
              return (
                <button
                  key={payment.id}
                  type="button"
                  onClick={() => setSelectedPayment(payment)}
                  className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-white/[0.025]"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-[#F5F5F7]">{payment.memo || 'OpenSplit invoice'}</p>
                    <p className="mt-1 text-xs text-[#94A3B8]">
                      {formatDateShort(payment.paid_at || payment.created_at)} · {completedSummary(payment)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <div className="text-right">
                      <p className="font-mono font-semibold text-[#F5F5F7]">{formatSats(payment.amount_sats)}</p>
                      {fiat && <p className="mt-0.5 font-mono text-xs text-[#94A3B8]">{fiat}</p>}
                    </div>
                    <Badge>{payoutStatusLabel(status)}</Badge>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </CardContent>

      <Dialog open={!!selectedPayment} onClose={() => setSelectedPayment(null)} title="Split Proof" className="max-w-3xl">
        {selectedPayment && (
          <SplitProofReceipt payment={selectedPayment} onRetrySplit={handleRetry} retrying={retrySplit.isPending} />
        )}
      </Dialog>
    </Card>
  );
}
