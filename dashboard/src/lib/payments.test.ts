import { describe, expect, it } from 'vitest';
import {
  btcpayPayoutsUrl,
  isWaitingInBtcpay,
  paymentIsWaitingInBtcpay,
  splitStatusLabel,
} from './payments';
import type { Invoice, PaymentSplit } from '@/types/api';

function split(partial: Partial<PaymentSplit>): PaymentSplit {
  return {
    id: 'split-1',
    label: 'Alice',
    ln_address: 'alice@example.com',
    amount_sats: 1000,
    status: 'in_progress',
    btcpay_payout_state: null,
    payout_id: 'payout-1',
    failure_reason: null,
    retry_count: 0,
    last_checked_at: null,
    executed_at: '2026-07-04T12:00:00Z',
    ...partial,
  };
}

function invoice(splits: PaymentSplit[]): Invoice {
  return {
    id: 'inv-1',
    bolt11: null,
    amount_sats: splits.reduce((s, x) => s + x.amount_sats, 0),
    fiat_amount: null,
    fiat_currency: null,
    memo: null,
    status: 'paid',
    paid_at: '2026-07-04T12:00:00Z',
    splits,
    created_at: '2026-07-04T12:00:00Z',
  };
}

describe('isWaitingInBtcpay', () => {
  it('is true only for in_progress splits parked awaiting approval/payment', () => {
    expect(isWaitingInBtcpay(split({ status: 'in_progress', btcpay_payout_state: 'AwaitingPayment' }))).toBe(true);
    expect(isWaitingInBtcpay(split({ status: 'in_progress', btcpay_payout_state: 'AwaitingApproval' }))).toBe(true);
  });

  it('is false when the mapped status is not in_progress', () => {
    expect(isWaitingInBtcpay(split({ status: 'completed', btcpay_payout_state: 'AwaitingPayment' }))).toBe(false);
    expect(isWaitingInBtcpay(split({ status: 'failed', btcpay_payout_state: 'AwaitingPayment' }))).toBe(false);
  });

  it('is false for other or missing raw states', () => {
    expect(isWaitingInBtcpay(split({ status: 'in_progress', btcpay_payout_state: 'InProgress' }))).toBe(false);
    expect(isWaitingInBtcpay(split({ status: 'in_progress', btcpay_payout_state: null }))).toBe(false);
  });
});

describe('splitStatusLabel', () => {
  it('shows "Waiting in BTCPay" for a parked split, otherwise the normal label', () => {
    expect(splitStatusLabel(split({ status: 'in_progress', btcpay_payout_state: 'AwaitingPayment' }))).toBe('Waiting in BTCPay');
    expect(splitStatusLabel(split({ status: 'in_progress', btcpay_payout_state: null }))).toBe('In progress');
    expect(splitStatusLabel(split({ status: 'completed' }))).toBe('Completed');
  });
});

describe('paymentIsWaitingInBtcpay', () => {
  it('is true when any split is parked and the payment rolls up to in_progress', () => {
    const p = invoice([
      split({ id: 'a', status: 'completed', btcpay_payout_state: 'Completed' }),
      split({ id: 'b', status: 'in_progress', btcpay_payout_state: 'AwaitingPayment' }),
    ]);
    expect(paymentIsWaitingInBtcpay(p)).toBe(true);
  });

  it('is false when a split has failed (rollup is failed, not in_progress)', () => {
    const p = invoice([
      split({ id: 'a', status: 'failed', btcpay_payout_state: 'AwaitingPayment' }),
      split({ id: 'b', status: 'in_progress', btcpay_payout_state: 'AwaitingPayment' }),
    ]);
    expect(paymentIsWaitingInBtcpay(p)).toBe(false);
  });

  it('is false when nothing is parked', () => {
    expect(paymentIsWaitingInBtcpay(invoice([split({ status: 'completed' })]))).toBe(false);
  });
});

describe('btcpayPayoutsUrl', () => {
  it('builds the payouts URL and rewrites host.docker.internal for the browser', () => {
    expect(
      btcpayPayoutsUrl('http://host.docker.internal:3003', 'store-abc', 'localhost')
    ).toBe('http://localhost:3003/stores/store-abc/payouts');
  });

  it('leaves reachable hosts untouched and trims a trailing slash', () => {
    expect(btcpayPayoutsUrl('https://btcpay.example.com/', 'store-1', 'localhost')).toBe(
      'https://btcpay.example.com/stores/store-1/payouts'
    );
  });

  it('returns null when the connection is not configured', () => {
    expect(btcpayPayoutsUrl(null, 'store-1', 'localhost')).toBeNull();
    expect(btcpayPayoutsUrl('https://btcpay.example.com', null, 'localhost')).toBeNull();
  });
});
