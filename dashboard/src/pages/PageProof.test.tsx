// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { Invoice, SplitProof } from '@/types/api';

// Hoisted, mutable state so each test can vary what the payment + proof hooks
// return without re-mocking the modules.
const h = vi.hoisted(() => ({
  invoice: {
    data: undefined as Invoice | undefined,
    isLoading: false,
    isError: false,
  },
  proof: {
    data: undefined as SplitProof | undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  },
}));

vi.mock('react-router-dom', () => ({
  useParams: () => ({ paymentId: 'pay-abc' }),
}));
vi.mock('@/hooks/useInvoices', () => ({
  useInvoice: () => h.invoice,
}));
vi.mock('@/hooks/useProof', () => ({
  useProof: () => h.proof,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ tenant: { tenant: { btcpay_url: null, btcpay_store_id: null } } }),
}));

import { PageProof } from './PageProof';

const PAYMENT: Invoice = {
  id: 'pay-abc',
  bolt11: null,
  amount_sats: 21001,
  fiat_amount: null,
  fiat_currency: null,
  memo: 'Carol + Dave split',
  status: 'paid',
  paid_at: '2026-06-01T12:00:00Z',
  created_at: '2026-06-01T11:59:00Z',
  splits: [
    {
      id: 'split-carol',
      label: 'Carol',
      ln_address: 'carol@example.com',
      amount_sats: 14001,
      status: 'completed',
      payout_id: 'po-1',
      failure_reason: null,
      retry_count: 0,
      last_checked_at: null,
      executed_at: '2026-06-01T12:00:05Z',
    },
    {
      id: 'split-dave',
      label: 'Dave',
      ln_address: 'dave@example.com',
      amount_sats: 7000,
      status: 'completed',
      payout_id: 'po-2',
      failure_reason: null,
      retry_count: 0,
      last_checked_at: null,
      executed_at: '2026-06-01T12:00:06Z',
    },
  ],
};

const PROOF: SplitProof = {
  payment_id: 'pay-abc',
  amount_sats: 21001,
  status: 'paid',
  split_rule_id: 'rule-1',
  split_rule_version: 3,
  members: [
    {
      split_id: 'split-carol',
      split_target_id: null,
      label: 'Carol',
      ln_address: 'carol@example.com',
      nostr_pubkey: null,
      percentage: 66.67,
      amount_sats: 14001,
      payout_status: 'completed',
      payout_id: 'po-1',
    },
    {
      split_id: 'split-dave',
      split_target_id: null,
      label: 'Dave',
      ln_address: 'dave@example.com',
      nostr_pubkey: null,
      percentage: 33.33,
      amount_sats: 7000,
      payout_status: 'completed',
      payout_id: 'po-2',
    },
  ],
  integrity: {
    payment_amount_sats: 21001,
    split_sum_sats: 21001,
    difference_sats: 0,
    balanced: true,
  },
};

afterEach(() => {
  cleanup();
  h.invoice = { data: undefined, isLoading: false, isError: false };
  h.proof = { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
});

describe('PageProof', () => {
  it('renders the Split Proof receipt for an owned payment', () => {
    h.invoice = { data: PAYMENT, isLoading: false, isError: false };
    h.proof = { data: PROOF, isLoading: false, isError: false, refetch: vi.fn() };

    render(<PageProof />);

    expect(screen.getByRole('heading', { name: 'Split Proof' })).toBeTruthy();
    // Balanced integrity + the sealed amount both surface from the proof/payment.
    expect(screen.getByText('Balance verified')).toBeTruthy();
    expect(screen.getAllByText('21,001 sats').length).toBeGreaterThan(0);
    expect(screen.getByText('Carol')).toBeTruthy();
    expect(screen.getByText('Dave')).toBeTruthy();
  });

  it('shows a clean not-found state when the payment 404s', () => {
    h.invoice = { data: undefined, isLoading: false, isError: true };

    render(<PageProof />);

    expect(screen.getByText('Proof not found')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Split Proof' })).toBeNull();
  });

  it('renders the footer app permalink, not the raw API path', () => {
    h.invoice = { data: PAYMENT, isLoading: false, isError: false };
    h.proof = { data: PROOF, isLoading: false, isError: false, refetch: vi.fn() };

    render(<PageProof />);

    expect(screen.getByText(`${window.location.origin}/proof/pay-abc`)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Copy proof link' })).toBeTruthy();
    expect(screen.queryByText('/payments/pay-abc/proof')).toBeNull();
  });
});
