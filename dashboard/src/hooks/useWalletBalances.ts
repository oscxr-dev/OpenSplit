import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { WalletBalance } from '@/types/api';

const TARGET_COLORS = [
  'bg-bitcoin',
  'bg-emerald-500',
  'bg-violet-500',
  'bg-rose-500',
  'bg-amber-500',
  'bg-cyan-500',
  'bg-pink-500',
  'bg-indigo-500',
];

type BalancesResponse = {
  wallets: WalletBalance[];
  total_accumulated_sats: number;
};

function normalizeBalancesResponse(data: unknown): BalancesResponse {
  if (Array.isArray(data)) {
    const wallets = data as WalletBalance[];
    return {
      wallets,
      total_accumulated_sats: wallets.reduce(
        (total, wallet) => total + (wallet.accumulated_sats ?? 0),
        0
      ),
    };
  }

  if (data && typeof data === 'object') {
    const response = data as Partial<BalancesResponse>;
    const wallets = Array.isArray(response.wallets) ? response.wallets : [];
    return {
      wallets,
      total_accumulated_sats:
        response.total_accumulated_sats ??
        wallets.reduce((total, wallet) => total + (wallet.accumulated_sats ?? 0), 0),
    };
  }

  return {
    wallets: [],
    total_accumulated_sats: 0,
  };
}

export function useWalletBalances() {
  return useQuery<BalancesResponse>({
    queryKey: ['walletBalances'],
    queryFn: async () => {
      const res = await api.get('/wallets/balances');
      return normalizeBalancesResponse(res.data);
    },
    staleTime: 1000 * 30,
    refetchInterval: 1000 * 60,
  });
}

export { TARGET_COLORS };
