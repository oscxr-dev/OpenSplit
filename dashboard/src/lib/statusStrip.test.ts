import { describe, expect, it } from 'vitest';
import { statusStripItems, type StatusStripItem } from './statusStrip';
import type { TenantStatus } from '@/types/api';

function base(overrides: Partial<TenantStatus> = {}): TenantStatus {
  return {
    store: 'ok',
    webhook: 'verified',
    active_rule: { name: 'Weekend split', version: 2 },
    payout_delivery: 'idle',
    public_page: 'on',
    ...overrides,
  };
}

function byKey(items: StatusStripItem[]) {
  return Object.fromEntries(items.map((item) => [item.key, item]));
}

describe('statusStripItems', () => {
  it('returns the five checks in order', () => {
    const items = statusStripItems(base(), { payoutsUrl: null });
    expect(items.map((i) => i.key)).toEqual([
      'store',
      'webhook',
      'active_rule',
      'payout_delivery',
      'public_page',
    ]);
  });

  it('maps a fully-green pipeline to ok tones', () => {
    const items = byKey(statusStripItems(base(), { payoutsUrl: null }));
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
        { payoutsUrl: null }
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
      statusStripItems(base({ store: 'unreachable', webhook: 'waiting' }), { payoutsUrl: null })
    );
    expect(items.store.tone).toBe('warn');
    expect(items.webhook.tone).toBe('warn');
  });

  it('surfaces waiting_in_btcpay as amber with the operator hint', () => {
    const items = byKey(
      statusStripItems(base({ payout_delivery: 'waiting_in_btcpay' }), {
        payoutsUrl: 'http://localhost:3003/stores/s/payouts',
      })
    );
    expect(items.payout_delivery.tone).toBe('warn');
    expect(items.payout_delivery.label).toBe('Waiting in BTCPay');
    expect(items.payout_delivery.hint).toContain('payout processor');
    expect(items.payout_delivery.href).toBe('http://localhost:3003/stores/s/payouts');
  });

  it('marks failing payouts red', () => {
    const items = byKey(
      statusStripItems(base({ payout_delivery: 'failing' }), { payoutsUrl: null })
    );
    expect(items.payout_delivery.tone).toBe('bad');
    expect(items.payout_delivery.label).toBe('Payouts failing');
  });

  it('deep-links each check to its fix', () => {
    const items = byKey(statusStripItems(base(), { payoutsUrl: null }));
    expect(items.store.to).toBe('/settings#connection');
    expect(items.webhook.to).toBe('/settings#connection');
    expect(items.active_rule.anchor).toBe('rule-board');
    expect(items.public_page.to).toBe('/settings#public-page');
  });
});
