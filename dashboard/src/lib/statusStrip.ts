/** Pure mapping from the aggregate tenant status to the Team page status-strip
 *  items: one entry per pipeline check, each carrying its tone, label, and the
 *  deep link that fixes it. Kept side-effect free so it can be unit-tested from
 *  fixtures (tones + hrefs) without rendering. */
import type { TenantStatus } from '@/types/api';
import i18n from '@/i18n';

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
  /** Actionable callout rendered beneath the strip — currently only for a
   *  missing Lightning payout processor. */
  guidance?: StatusStripGuidance;
}

export interface StatusStripGuidance {
  /** One-line plain-language explainer. */
  text: string;
  /** Label for the deep-link button. */
  fixLabel: string;
  /** External BTCPay URL the button opens (browser-rewritten). */
  fixHref: string;
}

/** Element id the rule-board section is tagged with on the Team page. */
export const RULE_BOARD_ANCHOR = 'rule-board';

export function statusStripItems(
  status: TenantStatus,
  opts: { payoutsUrl: string | null; payoutProcessorsUrl: string | null }
): StatusStripItem[] {
  const store: StatusStripItem = {
    key: 'store',
    to: '/settings#connection',
    ...(status.store === 'ok'
      ? { tone: 'ok', label: i18n.t('status.storeConnected') }
      : status.store === 'unreachable'
        ? { tone: 'warn', label: i18n.t('status.storeUnreachable') }
        : { tone: 'idle', label: i18n.t('status.storeNotSetUp') }),
  };

  const webhook: StatusStripItem = {
    key: 'webhook',
    to: '/settings#connection',
    ...(status.webhook === 'verified'
      ? { tone: 'ok', label: i18n.t('status.webhookVerified') }
      : status.webhook === 'waiting'
        ? { tone: 'warn', label: i18n.t('status.webhookWaiting') }
        : { tone: 'idle', label: i18n.t('status.webhookNotSetUp') }),
  };

  const activeRule: StatusStripItem = {
    key: 'active_rule',
    anchor: RULE_BOARD_ANCHOR,
    ...(status.active_rule
      ? { tone: 'ok', label: i18n.t('status.rule', { name: status.active_rule.name }) }
      : { tone: 'idle', label: i18n.t('status.noActiveRule') }),
  };

  const payout: StatusStripItem = {
    key: 'payout_delivery',
    ...(opts.payoutsUrl ? { href: opts.payoutsUrl } : {}),
    ...(status.payout_delivery === 'failing'
      ? { tone: 'bad', label: i18n.t('status.payoutsFailing') }
      : status.payout_delivery === 'waiting_in_btcpay'
        ? { tone: 'warn', label: i18n.t('payments.waitingInBtcpay'), hint: i18n.t('payments.waitingHint') }
        : status.payout_delivery === 'delivering'
          ? { tone: 'ok', label: i18n.t('status.deliveringPayouts') }
          : { tone: 'idle', label: i18n.t('status.payoutsIdle') }),
    // Only guide when we KNOW the processor is missing — never on "unknown" or
    // "active", so a key that can't read processors doesn't nag.
    ...(status.lightning_payout_processor === 'missing' && opts.payoutProcessorsUrl
      ? {
          guidance: {
            text: i18n.t('status.missingProcessorExplainer'),
            fixLabel: i18n.t('status.setupAutosend'),
            fixHref: opts.payoutProcessorsUrl,
          },
        }
      : {}),
  };

  const publicPage: StatusStripItem = {
    key: 'public_page',
    to: '/settings#public-page',
    ...(status.public_page === 'on'
      ? { tone: 'ok', label: i18n.t('status.publicPageOn') }
      : { tone: 'idle', label: i18n.t('status.publicPageOff') }),
  };

  return [store, webhook, activeRule, payout, publicPage];
}

/** Worst-state roll-up of the five checks into a single glanceable summary for
 *  the Team page pill. Derived from the SAME statusStripItems() tones so the
 *  compact summary and the full detail strip can never disagree. */
export type StatusSummaryTone = 'ok' | 'warn' | 'bad';

export interface StatusSummary {
  tone: StatusSummaryTone;
  /** Short, glanceable line — "Attention: {reason}" when red, the failing
   *  check's own label when amber, "Pipeline healthy" when all clear. */
  label: string;
}

/** Precedence, worst wins: any bad → red "Attention: …"; else any warn → amber
 *  with that check's label; else green "Pipeline healthy". Idle checks (nothing
 *  set up yet) are not failures and never downgrade the summary. */
export function summarizeStatus(items: StatusStripItem[]): StatusSummary {
  const bad = items.find((item) => item.tone === 'bad');
  if (bad) return { tone: 'bad', label: i18n.t('status.attention', { label: bad.label }) };
  const warn = items.find((item) => item.tone === 'warn');
  if (warn) return { tone: 'warn', label: warn.label };
  return { tone: 'ok', label: i18n.t('status.pipelineHealthy') };
}
