import type { Invoice } from '@/types/api';

/** Roll a payment's per-split statuses up into a single payout status. */
export function paymentPayoutStatus(payment: Invoice): string {
  if (payment.splits.some((split) => split.status === 'failed')) return 'failed';
  if (payment.splits.some((split) => ['pending', 'in_progress'].includes(split.status))) {
    return 'in_progress';
  }
  if (payment.splits.length && payment.splits.every((split) => split.status === 'completed')) {
    return 'completed';
  }
  return payment.status;
}

export function completedSummary(payment: Invoice): string {
  const completed = payment.splits.filter((split) => split.status === 'completed').length;
  return payment.splits.length ? `${completed}/${payment.splits.length} shares settled` : 'No split recorded';
}

export function splitTotal(payment: Invoice): number {
  return payment.splits.reduce((sum, split) => sum + split.amount_sats, 0);
}

export function hasProofMismatch(payment: Invoice): boolean {
  return payment.splits.length > 0 && splitTotal(payment) !== payment.amount_sats;
}

/** Old seeded/demo records are hidden from the live transaction views. */
export function isDemoHistoryPayment(payment: Invoice): boolean {
  const memo = (payment.memo || '').toLowerCase();
  return memo.includes('demo') || payment.splits.every((split) => split.status === 'cancelled');
}
