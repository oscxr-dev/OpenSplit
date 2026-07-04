/** Pure mapping from the aggregate tenant status to the Team page status-strip
 *  items: one entry per pipeline check, each carrying its tone, label, and the
 *  deep link that fixes it. Kept side-effect free so it can be unit-tested from
 *  fixtures (tones + hrefs) without rendering. */
import type { TenantStatus } from '@/types/api';
import { WAITING_IN_BTCPAY_HINT } from '@/lib/payments';

export type StatusTone = 'ok' | 'warn' | 'bad' | 'idle';

export type StatusStripKey =
  | 'store'
  | 'webhook'
  | 'active_rule'
  | 'payout_delivery'
  | 'public_page';

export interface StatusStripItem {
  key: StatusStripKey;
  tone: StatusTone;
  label: string;
  /** Internal SPA route (react-router) that fixes this check. */
  to?: string;
  /** External link (BTCPay), opened in a new tab. */
  href?: string;
  /** Same-page element id to scroll to (the rule board). */
  anchor?: string;
  /** Optional one-line hint rendered as a tooltip. */
  hint?: string;
}

/** Element id the rule-board section is tagged with on the Team page. */
export const RULE_BOARD_ANCHOR = 'rule-board';

export function statusStripItems(
  status: TenantStatus,
  opts: { payoutsUrl: string | null }
): StatusStripItem[] {
  const store: StatusStripItem = {
    key: 'store',
    to: '/settings#connection',
    ...(status.store === 'ok'
      ? { tone: 'ok', label: 'Store connected' }
      : status.store === 'unreachable'
        ? { tone: 'warn', label: 'Store unreachable' }
        : { tone: 'idle', label: 'Store not set up' }),
  };

  const webhook: StatusStripItem = {
    key: 'webhook',
    to: '/settings#connection',
    ...(status.webhook === 'verified'
      ? { tone: 'ok', label: 'Webhook verified' }
      : status.webhook === 'waiting'
        ? { tone: 'warn', label: 'Webhook waiting' }
        : { tone: 'idle', label: 'Webhook not set up' }),
  };

  const activeRule: StatusStripItem = {
    key: 'active_rule',
    anchor: RULE_BOARD_ANCHOR,
    ...(status.active_rule
      ? { tone: 'ok', label: `Rule: ${status.active_rule.name}` }
      : { tone: 'idle', label: 'No active rule' }),
  };

  const payout: StatusStripItem = {
    key: 'payout_delivery',
    ...(opts.payoutsUrl ? { href: opts.payoutsUrl } : {}),
    ...(status.payout_delivery === 'failing'
      ? { tone: 'bad', label: 'Payouts failing' }
      : status.payout_delivery === 'waiting_in_btcpay'
        ? { tone: 'warn', label: 'Waiting in BTCPay', hint: WAITING_IN_BTCPAY_HINT }
        : status.payout_delivery === 'delivering'
          ? { tone: 'ok', label: 'Delivering payouts' }
          : { tone: 'idle', label: 'Payouts idle' }),
  };

  const publicPage: StatusStripItem = {
    key: 'public_page',
    to: '/settings#public-page',
    ...(status.public_page === 'on'
      ? { tone: 'ok', label: 'Public page on' }
      : { tone: 'idle', label: 'Public page off' }),
  };

  return [store, webhook, activeRule, payout, publicPage];
}
