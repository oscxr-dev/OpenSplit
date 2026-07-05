import { describe, expect, it } from 'vitest';
import { statusStripItems, summarizeStatus, type StatusStripItem } from './statusStrip';
import type { TenantStatus } from '@/types/api';

const NO_URLS = { payoutsUrl: null, payoutProcessorsUrl: null };

function base(overrides: Partial<TenantStatus> = {}): TenantStatus {
  return {
    store: 'ok',
    webhook: 'verified',
    active_rule: { name: 'Weekend split', version: 2 },
    payout_delivery: 'idle',
    lightning_payout_processor: 'unknown',
    public_page: 'on',
    ...overrides,
  };
}

function byKey(items: StatusStripItem[]) {
  return Object.fromEntries(items.map((item) => [item.key, item]));
}

describe('statusStripItems', () => {
  it('returns the five checks in order', () => {
    const items = statusStripItems(base(), { payoutsUrl: null, payoutProcessorsUrl: null });
    expect(items.map((i) => i.key)).toEqual([
      'store',
      'webhook',
      'active_rule',
      'payout_delivery',
      'public_page',
    ]);
  });

  it('maps a fully-green pipeline to ok tones', () => {
    const items = byKey(statusStripItems(base(), { payoutsUrl: null, payoutProcessorsUrl: null }));
    expect(items.store.tone).toBe('ok');
    expect(items.webhook.tone).toBe('ok');
    expect(items.active_rule.tone).toBe('ok');
    expect(items.active_rule.label).toBe('Rule: Weekend split');
    expect(items.public_page.tone).toBe('ok');
  });

  it('maps unconfigured / idle states to idle tones', () => {
    const items = byKey(
      statusStripItems(
        base({
          store: 'not_configured',
          webhook: 'not_configured',
          active_rule: null,
          payout_delivery: 'idle',
          public_page: 'off',
        }),
        { payoutsUrl: null, payoutProcessorsUrl: null }
      )
    );
    expect(items.store.tone).toBe('idle');
    expect(items.webhook.tone).toBe('idle');
    expect(items.active_rule.tone).toBe('idle');
    expect(items.active_rule.label).toBe('No active rule');
    expect(items.public_page.tone).toBe('idle');
  });

  it('marks an unreachable store and a waiting webhook amber', () => {
    const items = byKey(
      statusStripItems(base({ store: 'unreachable', webhook: 'waiting' }), { payoutsUrl: null, payoutProcessorsUrl: null })
    );
    expect(items.store.tone).toBe('warn');
    expect(items.webhook.tone).toBe('warn');
  });

  it('surfaces waiting_in_btcpay as amber with the operator hint', () => {
    const items = byKey(
      statusStripItems(base({ payout_delivery: 'waiting_in_btcpay' }), {
        payoutsUrl: 'http://localhost:3003/stores/s/payouts',
        payoutProcessorsUrl: null,
      })
    );
    expect(items.payout_delivery.tone).toBe('warn');
    expect(items.payout_delivery.label).toBe('Waiting in BTCPay');
    expect(items.payout_delivery.hint).toContain('payout processor');
    expect(items.payout_delivery.href).toBe('http://localhost:3003/stores/s/payouts');
  });

  it('attaches missing-processor guidance only when the processor is missing', () => {
    const url = 'http://localhost:3003/stores/s/settings/payout-processors';
    const missing = byKey(
      statusStripItems(base({ lightning_payout_processor: 'missing' }), {
        payoutsUrl: null,
        payoutProcessorsUrl: url,
      })
    );
    expect(missing.payout_delivery.guidance).toEqual({
      text: expect.stringContaining('Lightning payout processor'),
      fixLabel: 'Set up auto-send in BTCPay',
      fixHref: url,
    });

    // No nagging when the state is "unknown" or "active".
    for (const state of ['unknown', 'active'] as const) {
      const items = byKey(
        statusStripItems(base({ lightning_payout_processor: state }), {
          payoutsUrl: null,
          payoutProcessorsUrl: url,
        })
      );
      expect(items.payout_delivery.guidance).toBeUndefined();
    }
  });

  it('omits guidance when the processors URL is unavailable', () => {
    const items = byKey(
      statusStripItems(base({ lightning_payout_processor: 'missing' }), {
        payoutsUrl: null,
        payoutProcessorsUrl: null,
      })
    );
    expect(items.payout_delivery.guidance).toBeUndefined();
  });

  it('marks failing payouts red', () => {
    const items = byKey(
      statusStripItems(base({ payout_delivery: 'failing' }), { payoutsUrl: null, payoutProcessorsUrl: null })
    );
    expect(items.payout_delivery.tone).toBe('bad');
    expect(items.payout_delivery.label).toBe('Payouts failing');
  });

  it('deep-links each check to its fix', () => {
    const items = byKey(statusStripItems(base(), { payoutsUrl: null, payoutProcessorsUrl: null }));
    expect(items.store.to).toBe('/settings#connection');
    expect(items.webhook.to).toBe('/settings#connection');
    expect(items.active_rule.anchor).toBe('rule-board');
    expect(items.public_page.to).toBe('/settings#public-page');
  });
});

describe('summarizeStatus', () => {
  it('reports "Pipeline healthy" when every check is ok', () => {
    const summary = summarizeStatus(statusStripItems(base(), NO_URLS));
    expect(summary).toEqual({ tone: 'ok', label: 'Pipeline healthy' });
  });

  it('treats an all-idle (nothing set up) pipeline as healthy, not a failure', () => {
    const summary = summarizeStatus(
      statusStripItems(
        base({
          store: 'not_configured',
          webhook: 'not_configured',
          active_rule: null,
          payout_delivery: 'idle',
          public_page: 'off',
        }),
        NO_URLS
      )
    );
    expect(summary).toEqual({ tone: 'ok', label: 'Pipeline healthy' });
  });

  it('surfaces a single warning amber with that check\'s own label', () => {
    const summary = summarizeStatus(statusStripItems(base({ webhook: 'waiting' }), NO_URLS));
    expect(summary).toEqual({ tone: 'warn', label: 'Webhook waiting' });
  });

  it('surfaces a failing payout red with an "Attention:" prefix', () => {
    const summary = summarizeStatus(
      statusStripItems(base({ payout_delivery: 'failing' }), NO_URLS)
    );
    expect(summary).toEqual({ tone: 'bad', label: 'Attention: Payouts failing' });
  });

  it('lets bad win over warn (worst-state precedence)', () => {
    // Store unreachable (warn) AND payouts failing (bad): red wins.
    const summary = summarizeStatus(
      statusStripItems(base({ store: 'unreachable', payout_delivery: 'failing' }), NO_URLS)
    );
    expect(summary.tone).toBe('bad');
    expect(summary.label).toBe('Attention: Payouts failing');
  });

  it('lets warn win over ok/idle when no check is bad', () => {
    // Store unreachable (warn) alongside otherwise-healthy checks: amber wins,
    // and the label is the first failing check encountered (store).
    const summary = summarizeStatus(statusStripItems(base({ store: 'unreachable' }), NO_URLS));
    expect(summary).toEqual({ tone: 'warn', label: 'Store unreachable' });
  });

  it('reports the amber label for a payout waiting in BTCPay', () => {
    const summary = summarizeStatus(
      statusStripItems(base({ payout_delivery: 'waiting_in_btcpay' }), NO_URLS)
    );
    expect(summary).toEqual({ tone: 'warn', label: 'Waiting in BTCPay' });
  });
});
