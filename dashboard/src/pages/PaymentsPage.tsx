import { useEffect, useMemo, useState } from 'react';
import { ReceiptText, Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useInvoices, useRetryPaymentSplit } from '@/hooks/useInvoices';
import { SplitProofReceipt } from '@/components/payments/SplitProofReceipt';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { cn, formatDateShort, formatFiat, formatSats, payoutStatusLabel } from '@/lib/utils';
import {
  completedSummary,
  hasProofMismatch,
  isDemoHistoryPayment,
  paymentPayoutStatus,
} from '@/lib/payments';
import type { Invoice, PaymentSplit } from '@/types/api';

type StatusFilter = 'all' | 'completed' | 'in_progress' | 'failed';

const statuses: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'completed', label: 'Completed' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'failed', label: 'Failed' },
];

export function PaymentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialStatus = searchParams.get('status') as StatusFilter | null;
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(
    statuses.some((status) => status.value === initialStatus) ? initialStatus! : 'all'
  );
  const [search, setSearch] = useState('');
  const [selectedPayment, setSelectedPayment] = useState<Invoice | null>(null);
  const retrySplit = useRetryPaymentSplit();

  const { data, isLoading, isError, refetch } = useInvoices({
    status: statusFilter === 'all' ? undefined : statusFilter,
    search: search || undefined,
    limit: 100,
  });
  const payments = useMemo(() => data?.items || [], [data]);
  const livePayments = useMemo(
    () => payments.filter((payment) => !isDemoHistoryPayment(payment)),
    [payments]
  );
  const demoPayments = useMemo(
    () => payments.filter((payment) => isDemoHistoryPayment(payment)),
    [payments]
  );
  const [showDemoHistory, setShowDemoHistory] = useState(false);

  useEffect(() => {
    const requestedId = searchParams.get('payment');
    if (requestedId && payments.length) {
      const match = payments.find((payment) => payment.id === requestedId);
      if (match) setSelectedPayment(match);
    }
  }, [payments, searchParams]);

  function selectStatus(status: StatusFilter) {
    setStatusFilter(status);
    const next = new URLSearchParams(searchParams);
    if (status === 'all') next.delete('status');
    else next.set('status', status);
    setSearchParams(next, { replace: true });
  }

  function openPayment(payment: Invoice) {
    setSelectedPayment(payment);
    const next = new URLSearchParams(searchParams);
    next.set('payment', payment.id);
    setSearchParams(next, { replace: true });
  }

  function closePayment() {
    setSelectedPayment(null);
    const next = new URLSearchParams(searchParams);
    next.delete('payment');
    setSearchParams(next, { replace: true });
  }

  async function handleRetry(split: PaymentSplit) {
    if (!selectedPayment) return;
    const confirmed = window.confirm(
      `Retry ${formatSats(split.amount_sats)} payout to ${split.label || 'this partner'}?`
    );
    if (!confirmed) return;

    try {
      const updated = await retrySplit.mutateAsync({
        paymentId: selectedPayment.id,
        splitId: split.id,
      });
      setSelectedPayment({
        ...selectedPayment,
        splits: selectedPayment.splits.map((item) => item.id === split.id ? updated : item),
      });
      toast.success('Payout retry started.');
    } catch {
      toast.error('Could not retry payout.');
    }
  }

  function renderPaymentRows(rows: Invoice[], options: { demo?: boolean } = {}) {
    return rows.map((payment) => {
      const status = paymentPayoutStatus(payment);
      const mismatch = hasProofMismatch(payment);
      const fiat = formatFiat(payment.fiat_amount, payment.fiat_currency);

      return (
        <tr
          key={payment.id}
          className={cn(
            'cursor-pointer transition hover:bg-white/[0.025]',
            options.demo && 'bg-white/[0.012] opacity-75'
          )}
          onClick={() => openPayment(payment)}
        >
          <td className="px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-[#F5F5F7]">{payment.memo || 'OpenSplit invoice'}</p>
              {options.demo && <Badge variant="default">Demo history</Badge>}
            </div>
            <p className="mt-1 font-mono text-xs text-[#94A3B8]">{payment.id}</p>
          </td>
          <td className="px-5 py-4">
            <p className="font-mono font-semibold text-[#F5F5F7]">{formatSats(payment.amount_sats)}</p>
            {fiat && <p className="mt-1 font-mono text-xs text-[#94A3B8]">{fiat}</p>}
          </td>
          <td className="px-5 py-4 font-mono text-xs text-[#94A3B8]">
            {formatDateShort(payment.paid_at || payment.created_at)}
          </td>
          <td className="px-5 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={mismatch ? 'warning' : undefined}>
                {mismatch ? 'Proof mismatch' : payoutStatusLabel(status)}
              </Badge>
              <span className="text-xs text-[#94A3B8]">
                {options.demo ? 'Hidden from live flow' : completedSummary(payment)}
              </span>
            </div>
          </td>
        </tr>
      );
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Could not load payments" onRetry={() => refetch()} />;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight text-[#F5F5F7] sm:text-5xl">
            Recent payments
          </h1>
        </div>

        <div className="relative w-full lg:max-w-sm">
          <Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-[#94A3B8]" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search invoice memo"
            className="min-h-11 pl-10"
          />
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {statuses.map((status) => (
          <button
            key={status.value}
            onClick={() => selectStatus(status.value)}
            className={cn(
              'min-h-10 whitespace-nowrap rounded-md px-4 text-sm font-semibold transition-colors',
              statusFilter === status.value
                ? 'border border-[#FF2D78]/28 bg-[#FF2D78]/12 text-[#F5F5F7]'
                : 'border border-white/[0.08] bg-white/[0.035] text-[#94A3B8] hover:bg-white/[0.07] hover:text-[#F5F5F7]'
            )}
          >
            {status.label}
          </button>
        ))}
      </div>

      {!livePayments.length ? (
        <EmptyState
          icon={<ReceiptText className="h-8 w-8 text-[#94A3B8]" />}
          message={statusFilter === 'all' ? 'No live payments yet' : 'No live payments match this status'}
          description={demoPayments.length ? 'Old demo records are tucked into Demo history below.' : 'Paid invoices will appear here with their split proof status.'}
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="flex items-center gap-3 border-b border-white/[0.06] p-5">
              <ReceiptText className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
              <div>
                <h2 className="font-semibold text-[#F5F5F7]">Live payment records</h2>
                <p className="mt-1 text-sm text-[#94A3B8]">{livePayments.length} current BTCPay records</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b border-white/[0.06] text-xs uppercase tracking-[0.12em] text-[#94A3B8]">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Invoice</th>
                    <th className="px-5 py-3 font-semibold">Amount</th>
                    <th className="px-5 py-3 font-semibold">Paid</th>
                    <th className="px-5 py-3 font-semibold">Proof</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06]">
                  {renderPaymentRows(livePayments)}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {!!demoPayments.length && (
        <Card className="border-white/[0.05] bg-white/[0.02] shadow-none">
          <CardContent className="p-0">
            <button
              type="button"
              onClick={() => setShowDemoHistory((value) => !value)}
              className="flex w-full items-center justify-between gap-4 p-5 text-left transition hover:bg-white/[0.025]"
            >
              <div>
                <h2 className="font-semibold text-[#F5F5F7]">Demo history</h2>
                <p className="mt-1 text-sm text-[#94A3B8]">
                  {demoPayments.length} old test records hidden from the live flow.
                </p>
              </div>
              <span className="rounded-full border border-white/[0.08] px-3 py-1 text-xs font-semibold text-[#94A3B8]">
                {showDemoHistory ? 'Hide' : 'Show'}
              </span>
            </button>

            {showDemoHistory && (
              <div className="overflow-x-auto border-t border-white/[0.06]">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="border-b border-white/[0.06] text-xs uppercase tracking-[0.12em] text-[#94A3B8]">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Invoice</th>
                      <th className="px-5 py-3 font-semibold">Amount</th>
                      <th className="px-5 py-3 font-semibold">Paid</th>
                      <th className="px-5 py-3 font-semibold">Proof</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {renderPaymentRows(demoPayments, { demo: true })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Dialog open={!!selectedPayment} onClose={closePayment} title="Split Proof" className="max-w-3xl">
        {selectedPayment && (
          <SplitProofReceipt
            payment={selectedPayment}
            onRetrySplit={handleRetry}
            retrying={retrySplit.isPending}
          />
        )}
      </Dialog>
    </div>
  );
}
