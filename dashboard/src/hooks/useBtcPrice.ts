import { useQuery } from '@tanstack/react-query';

const SATS_PER_BTC = 100_000_000;

async function fetchBtcPrice(): Promise<number> {
  const res = await fetch(
    'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd'
  );
  if (!res.ok) throw new Error('Failed to fetch BTC price');
  const data = await res.json();
  return data.bitcoin.usd as number;
}

export function useBtcPrice() {
  return useQuery<number>({
    queryKey: ['btcPrice'],
    queryFn: fetchBtcPrice,
    staleTime: 1000 * 60 * 5,  // 5 min cache
    refetchInterval: 1000 * 60 * 5,
    retry: 3,
    retryDelay: 2000,
  });
}

export function satsToUsd(sats: number, btcPrice: number): number {
  return (sats / SATS_PER_BTC) * btcPrice;
}
