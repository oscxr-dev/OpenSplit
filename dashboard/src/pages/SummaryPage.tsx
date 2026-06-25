import { AlertCircle, ArrowRight, CircleDollarSign, RadioTower, ReceiptText, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/shared/ErrorState';
import { useDashboardSummary } from '@/hooks/useDashboard';
import { getGreeting } from '@/lib/greeting';
import { formatDateShort, formatFiat, formatSats, payoutStatusLabel } from '@/lib/utils';

export function SummaryPage() {
  const { data, isLoading, isError, refetch } = useDashboardSummary();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-40 w-full" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return <ErrorState message="Could not load summary" onRetry={() => refetch()} />;
  }

  const fiat = formatFiat(data.today.total_fiat, data.today.fiat_currency);
  const greeting = getGreeting();

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium tracking-[0.12em] text-white/35 uppercase">Node status</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white/90 sm:text-3xl">{greeting}</h1>
          <p className="mt-1 text-sm text-white/40">Here is how your business is moving today.</p>
        </div>
        <Link
          to="/pos"
          className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-white px-5 text-sm font-semibold text-[#18141f] shadow-[0_10px_28px_rgba(0,0,0,0.2)] transition-transform hover:-translate-y-0.5 active:scale-[0.98]"
        >
          <Zap className="h-4 w-4 text-orange-500" />
          New payment
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-500">Today&apos;s sales</p>
              <div className="rounded-xl border border-orange-300/10 bg-orange-400/10 p-2.5 text-orange-300">
                <CircleDollarSign className="h-5 w-5" />
              </div>
            </div>
            <p className="mt-5 text-3xl font-bold tracking-tight text-gray-950">
              {formatSats(data.today.total_sats)}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              {data.today.count} {data.today.count === 1 ? 'payment' : 'payments'}
              {fiat ? ` · ${fiat}` : ''}
            </p>
          </CardContent>
        </Card>

        <Card className={data.failed_count > 0 ? 'border-red-200 bg-red-50/40' : ''}>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-500">Splits needing attention</p>
              <div className={`rounded-xl border p-2.5 ${data.failed_count ? 'border-red-300/10 bg-red-400/10 text-red-300' : 'border-emerald-300/10 bg-emerald-400/10 text-emerald-300'}`}>
                <AlertCircle className="h-5 w-5" />
              </div>
            </div>
            <p className="mt-5 text-3xl font-bold text-gray-950">{data.failed_count}</p>
            <Link
              to="/payments?status=failed"
              className="mt-2 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-red-700"
            >
              {data.failed_count ? 'Review failed' : 'All clear'}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>
      </div>

      <Card className="relative overflow-hidden !border-white/10 !bg-gradient-to-br !from-violet-500/15 !via-white/[0.03] !to-orange-400/[0.07]">
        <CardContent className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium tracking-wider text-white/40 uppercase">Lightning</p>
              <h2 className="mt-1 text-lg font-semibold">Channel integration pending</h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-white/45">
                Receive and send capacity will appear once the LND balance is connected.
              </p>
              <Link
                to="/wallets"
                className="mt-3 inline-flex min-h-10 items-center gap-2 text-sm font-medium text-orange-200 transition-colors hover:text-white"
              >
                View liquidity <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.07] p-3">
              <RadioTower className="h-5 w-5 text-amber-300" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div>
              <h2 className="font-semibold text-gray-950">Recent payments</h2>
              <p className="text-sm text-gray-500">Updates automatically every 10 seconds</p>
            </div>
            <ReceiptText className="h-5 w-5 text-gray-400" />
          </div>

          {data.recent_payments.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-gray-500">
              No payments recorded yet.
            </p>
          ) : (
            <div className="divide-y divide-gray-100">
              {data.recent_payments.map((payment) => (
                <Link
                  key={payment.id}
                  to={`/payments?payment=${payment.id}`}
                  className="flex min-h-20 items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-gray-50"
                >
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-950">{formatSats(payment.amount_sats)}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      {formatDateShort(payment.paid_at)} · {payment.splits_summary}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge>{payoutStatusLabel(payment.status)}</Badge>
                    <ArrowRight className="h-4 w-4 text-gray-400" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
