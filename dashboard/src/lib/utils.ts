import { format, parseISO } from 'date-fns';
import { enUS } from 'date-fns/locale';

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function formatSats(sats: number): string {
  return new Intl.NumberFormat('en-US').format(sats) + ' sats';
}

export function formatFiat(amount: number | null, currency: string | null): string | null {
  if (amount === null || !currency) return null;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function payoutStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    paid: 'Paid',
    pending: 'Pending',
    in_progress: 'In progress',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };
  return labels[status] || status;
}

export function formatSatsCompact(sats: number): string {
  if (sats >= 1_000_000) {
    const m = (sats / 1_000_000).toFixed(1);
    return m.replace(/\.0$/, '') + 'M sats';
  }
  if (sats >= 1_000) {
    const k = (sats / 1_000).toFixed(1);
    return k.replace(/\.0$/, '') + 'K sats';
  }
  return sats.toString() + ' sats';
}

export function formatDate(date: string | null): string {
  if (!date) return '—';
  try {
    return format(parseISO(date), 'dd MMM yyyy HH:mm', { locale: enUS });
  } catch {
    return '—';
  }
}

export function formatDateShort(date: string | null): string {
  if (!date) return '—';
  try {
    return format(parseISO(date), 'MM/dd HH:mm', { locale: enUS });
  } catch {
    return '—';
  }
}

export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}
