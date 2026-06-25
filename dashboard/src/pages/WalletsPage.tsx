import { Wallet } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { ErrorState } from '@/components/shared/ErrorState';
import { formatSats } from '@/lib/utils';
import { useWalletBalances, TARGET_COLORS } from '@/hooks/useWalletBalances';

export function WalletsPage() {
  const { data, isLoading, isError, refetch } = useWalletBalances();
  const wallets = data?.wallets ?? [];
  const totalAccumulatedSats = data?.total_accumulated_sats ?? 0;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="Could not load wallets" onRetry={() => refetch()} />;
  }

  if (wallets.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <p className="text-xs font-medium tracking-[0.12em] text-white/35 uppercase">Balances</p>
          <h1 className="mt-1 text-2xl font-semibold text-white/90 sm:text-3xl">Liquidity</h1>
        </div>
        <EmptyState
          icon={<Wallet className="w-8 h-8 text-gray-400" />}
          message="No active split rule"
          description="Activate a split rule to see each wallet balance"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium tracking-[0.12em] text-white/35 uppercase">Balances</p>
        <h1 className="mt-1 text-2xl font-semibold text-white/90 sm:text-3xl">Liquidity</h1>
      </div>

      {/* Total card */}
      <Card className="border-orange-300/15 bg-gradient-to-br from-orange-400/25 via-orange-500/10 to-violet-500/10 text-white">
        <CardContent className="pt-6">
          <p className="text-sm text-white/80 mb-1">Total accumulated</p>
          <p className="text-3xl font-bold">{formatSats(totalAccumulatedSats)}</p>
        </CardContent>
      </Card>

      {/* Wallet cards */}
      <div className="space-y-3">
        {wallets.map((wallet) => (
          <Card key={wallet.lnbits_wallet_id}>
            <CardContent className="pt-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={`w-4 h-4 rounded-full ${TARGET_COLORS[wallet.color_index % TARGET_COLORS.length]} flex-shrink-0`}
                  />
                  <div>
                    <h3 className="font-semibold text-gray-900">{wallet.label}</h3>
                    <p className="text-xs text-gray-400 font-mono">
                      {wallet.lnbits_wallet_id.slice(0, 12)}...
                    </p>
                  </div>
                </div>
                <span className="text-sm font-medium text-gray-500">{wallet.percentage}%</span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-4 pt-3 border-t border-gray-100">
                <div>
                  <span className="text-xs text-gray-400">Accumulated</span>
                  <p className="text-lg font-bold text-gray-900">
                    {formatSats(wallet.accumulated_sats)}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-gray-400">
                    Balance {wallet.current_balance_sats !== null ? 'current' : '(unavailable)'}
                  </span>
                  <p className="text-lg font-bold text-gray-900">
                    {wallet.current_balance_sats !== null
                      ? formatSats(wallet.current_balance_sats)
                      : '—'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
