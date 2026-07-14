import type { Invoice } from '@/types/api';
import i18n from '@/i18n';
import { payoutStatusLabel } from '@/lib/utils';
import { toBrowserUrl } from '@/lib/browserUrl';

/** Raw BTCPay payout states meaning "BTCPay is holding this payout" — it needs
 *  a manual send or a Lightning payout processor before it can settle. */
const WAITING_BTCPAY_STATES = ['AwaitingApproval', 'AwaitingPayment'];

/** True when a split is mapped to in_progress but BTCPay's raw state shows it
 *  is parked awaiting approval/payment — i.e. stuck until the operator acts. */
export function isWaitingInBtcpay(split: {
  status: string;
  btcpay_payout_state?: string | null;
}): boolean {
  return (
    split.status === 'in_progress' &&
    !!split.btcpay_payout_state &&
    WAITING_BTCPAY_STATES.includes(split.btcpay_payout_state)
  );
}

/** Human status for one split: "Waiting in BTCPay" when parked in BTCPay,
 *  otherwise the normal payout status label. */
export function splitStatusLabel(split: {
  status: string;
  btcpay_payout_state?: string | null;
}): string {
  return isWaitingInBtcpay(split) ? i18n.t('payments.waitingInBtcpay') : payoutStatusLabel(split.status);
}

/** Browser-openable link to a store's BTCPay payouts screen (host.docker.internal
 *  rewritten), or null when the BTCPay connection isn't configured. */
export function btcpayPayoutsUrl(
  btcpayUrl: string | null | undefined,
  storeId: string | null | undefined,
  browserHostname: string
): string | null {
  if (!btcpayUrl || !storeId) return null;
  const base = btcpayUrl.replace(/\/+$/, '');
  return toBrowserUrl(`${base}/stores/${storeId}/payouts`, browserHostname);
}

/** Browser-openable link to a store's BTCPay payout-processors settings screen
 *  (host.docker.internal rewritten), or null when the connection isn't set. This
 *  is where the operator enables the Lightning payout processor that auto-sends
 *  payouts. */
export function btcpayPayoutProcessorsUrl(
  btcpayUrl: string | null | undefined,
  storeId: string | null | undefined,
  browserHostname: string
): string | null {
  if (!btcpayUrl || !storeId) return null;
  const base = btcpayUrl.replace(/\/+$/, '');
  return toBrowserUrl(
    `${base}/stores/${storeId}/settings/payout-processors`,
    browserHostname
  );
}

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

/** True when a payment is mapped in_progress but at least one split is parked
 *  awaiting action in BTCPay — surfaced so the row reads "Waiting in BTCPay"
 *  instead of a bare "In progress". */
export function paymentIsWaitingInBtcpay(payment: Invoice): boolean {
  return (
    paymentPayoutStatus(payment) === 'in_progress' &&
    payment.splits.some((split) => isWaitingInBtcpay(split))
  );
}

export function completedSummary(payment: Invoice): string {
  const completed = payment.splits.filter((split) => split.status === 'completed').length;
  return payment.splits.length
    ? i18n.t('payments.sharesSettled', { completed, count: payment.splits.length })
    : i18n.t('payments.noSplitRecorded');
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
