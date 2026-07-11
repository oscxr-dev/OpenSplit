// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { Invoice, SplitProof } from '@/types/api';

// Hoisted, mutable proof-hook state so each test can vary the proof payload
// without re-mocking the module.
const h = vi.hoisted(() => ({
  proof: {
    data: undefined as SplitProof | undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  },
}));

vi.mock('@/hooks/useProof', () => ({
  useProof: () => h.proof,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ tenant: { tenant: { btcpay_url: null, btcpay_store_id: null } } }),
}));

import { SplitProofReceipt } from './SplitProofReceipt';

const PREIMAGE = 'c6aa922406355f1f201daea3e46d451576657016026dfe4872bf47835e08b75e';
const PAYMENT_HASH = '77850d754d7177072f799a77cf6886f79adc029ecc02a52d781b3959af430ffe';

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
      status: 'in_progress',
      payout_id: 'po-2',
      failure_reason: null,
      retry_count: 0,
      last_checked_at: null,
      executed_at: '2026-06-01T12:00:06Z',
    },
  ],
};

function proofWith(members: Partial<SplitProof['members'][number]>[]): SplitProof {
  return {
    payment_id: 'pay-abc',
    amount_sats: 21001,
    status: 'paid',
    split_rule_id: 'rule-1',
    split_rule_version: 3,
    members: members.map((overrides, i) => ({
      split_id: i === 0 ? 'split-carol' : 'split-dave',
      split_target_id: null,
      label: i === 0 ? 'Carol' : 'Dave',
      ln_address: null,
      nostr_pubkey: null,
      percentage: null,
      amount_sats: i === 0 ? 14001 : 7000,
      payout_status: i === 0 ? 'completed' : 'in_progress',
      payout_id: null,
      ...overrides,
    })),
    integrity: {
      payment_amount_sats: 21001,
      split_sum_sats: 21001,
      difference_sats: 0,
      balanced: true,
    },
  };
}

afterEach(() => {
  cleanup();
  h.proof = { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
  vi.restoreAllMocks();
});

describe('SplitProofReceipt Lightning settlement proof', () => {
  it('shows the preimage affordance only for the completed split that has one', () => {
    h.proof = {
      data: proofWith([
        { ln_preimage: PREIMAGE, ln_payment_hash: PAYMENT_HASH },
        {},
      ]),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    // Exactly one affordance: Carol (completed + preimage), not Dave (in progress).
    expect(screen.getAllByText('Lightning settlement proof')).toHaveLength(1);
    // Truncated preimage and payment hash are rendered.
    expect(screen.getByText(`preimage ${PREIMAGE.slice(0, 18)}…${PREIMAGE.slice(-10)}`)).toBeTruthy();
    expect(screen.getByText(`hash ${PAYMENT_HASH.slice(0, 18)}…${PAYMENT_HASH.slice(-10)}`)).toBeTruthy();
  });

  it('hides the affordance for a completed split without a recorded preimage', () => {
    h.proof = {
      data: proofWith([{}, {}]),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    expect(screen.queryByText('Lightning settlement proof')).toBeNull();
    expect(screen.queryByRole('button', { name: /Copy preimage/ })).toBeNull();
  });

  it('never shows a preimage on a non-completed split, even if the API sent one', () => {
    h.proof = {
      data: proofWith([
        {},
        { ln_preimage: PREIMAGE, ln_payment_hash: PAYMENT_HASH },
      ]),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    expect(screen.queryByText('Lightning settlement proof')).toBeNull();
  });

  it('copies the full, untruncated preimage to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    h.proof = {
      data: proofWith([{ ln_preimage: PREIMAGE, ln_payment_hash: PAYMENT_HASH }, {}]),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    fireEvent.click(screen.getByRole('button', { name: /Copy preimage/ }));
    expect(writeText).toHaveBeenCalledWith(PREIMAGE);
  });
});
