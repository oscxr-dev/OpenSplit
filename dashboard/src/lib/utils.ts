import { format, parseISO } from 'date-fns';
import i18n, { dateFnsLocale } from '@/i18n';

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

const PAYOUT_STATUS_KEYS: Record<string, string> = {
  paid: 'payments.status.paid',
  pending: 'payments.status.pending',
  in_progress: 'payments.status.inProgress',
  completed: 'payments.status.completed',
  failed: 'payments.status.failed',
  cancelled: 'payments.status.cancelled',
};

export function payoutStatusLabel(status: string): string {
  const key = PAYOUT_STATUS_KEYS[status];
  return key ? i18n.t(key) : status;
}

/** Badge variant for a raw payout status — keyed on the status itself so it
 *  stays correct regardless of the UI language the label is rendered in. */
export function payoutStatusVariant(status: string): 'default' | 'success' | 'warning' | 'error' {
  if (status === 'paid' || status === 'completed') return 'success';
  if (status === 'pending' || status === 'in_progress') return 'warning';
  if (status === 'failed' || status === 'cancelled') return 'error';
  return 'default';
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
    return format(parseISO(date), 'dd MMM yyyy HH:mm', { locale: dateFnsLocale() });
  } catch {
    return '—';
  }
}

export function formatDateShort(date: string | null): string {
  if (!date) return '—';
  try {
    return format(parseISO(date), 'MM/dd HH:mm', { locale: dateFnsLocale() });
  } catch {
    return '—';
  }
}

export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}
