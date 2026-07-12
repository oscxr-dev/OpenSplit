// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { Invoice, SplitProof } from '@/types/api';

// Hoisted, mutable hook state so each test can vary the proof payload, the
// tenant (Nostr key configured or not), and the sign mutation without
// re-mocking the modules.
const h = vi.hoisted(() => ({
  proof: {
    data: undefined as SplitProof | undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  },
  sign: { mutate: vi.fn(), isPending: false },
  tenantOverrides: {} as Record<string, unknown>,
}));

vi.mock('@/hooks/useProof', () => ({
  useProof: () => h.proof,
  useSignProof: () => h.sign,
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    tenant: {
      tenant: { btcpay_url: null, btcpay_store_id: null, ...h.tenantOverrides },
    },
  }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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

function proofWith(
  members: Partial<SplitProof['members'][number]>[],
  overrides: Partial<SplitProof> = {}
): SplitProof {
  return {
    payment_id: 'pay-abc',
    amount_sats: 21001,
    status: 'paid',
    split_rule_id: 'rule-1',
    split_rule_version: 3,
    rule_fingerprint: null,
    ...overrides,
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
  h.sign = { mutate: vi.fn(), isPending: false };
  h.tenantOverrides = {};
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

const FINGERPRINT = 'bc0c49b1591b2d47dbaf19324e09fdf78517114e314b4346ed39cb5397b322aa';

describe('SplitProofReceipt rule fingerprint', () => {
  it('renders the truncated fingerprint when the proof carries one', () => {
    h.proof = {
      data: proofWith([{}, {}], { rule_fingerprint: FINGERPRINT }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    expect(screen.getByText('Rule fingerprint (SHA-256)')).toBeTruthy();
    expect(
      screen.getByText(`${FINGERPRINT.slice(0, 18)}…${FINGERPRINT.slice(-10)}`)
    ).toBeTruthy();
  });

  it('hides the fingerprint block when the proof has none (old payments)', () => {
    h.proof = {
      data: proofWith([{}, {}], { rule_fingerprint: null }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    expect(screen.queryByText('Rule fingerprint (SHA-256)')).toBeNull();
    expect(screen.queryByRole('button', { name: /Copy fingerprint/ })).toBeNull();
  });

  it('copies the full, untruncated fingerprint to the clipboard', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    h.proof = {
      data: proofWith([{}, {}], { rule_fingerprint: FINGERPRINT }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    fireEvent.click(screen.getByRole('button', { name: /Copy fingerprint/ }));
    expect(writeText).toHaveBeenCalledWith(FINGERPRINT);
  });
});

const NOSTR_PUBKEY = '3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d';
const NOSTR_NPUB = 'npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6';
const NOSTR_EVENT_ID = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90';
const NOSTR_EVENT_JSON = JSON.stringify({
  pubkey: NOSTR_PUBKEY,
  created_at: 1780000000,
  kind: 2718,
  tags: [['t', 'opensplit-proof']],
  content: '{"spec":"opensplit-split-proof/v1"}',
  id: NOSTR_EVENT_ID,
  sig: 'ff'.repeat(64),
});
const NOSTR_PROOF = {
  event_json: NOSTR_EVENT_JSON,
  event_id: NOSTR_EVENT_ID,
  pubkey: NOSTR_PUBKEY,
  npub: NOSTR_NPUB,
  kind: 2718,
  created_at: 1780000000,
};

describe('SplitProofReceipt Nostr signature', () => {
  it('offers Sign proof only when paid, key configured, and not yet signed', () => {
    h.tenantOverrides = { nostr_pubkey: NOSTR_PUBKEY, nostr_npub: NOSTR_NPUB };
    h.proof = { data: proofWith([{}, {}]), isLoading: false, isError: false, refetch: vi.fn() };

    render(<SplitProofReceipt payment={PAYMENT} />);

    fireEvent.click(screen.getByRole('button', { name: 'Sign proof' }));
    expect(h.sign.mutate).toHaveBeenCalledTimes(1);
  });

  it('hides the sign action when the team has no Nostr key configured', () => {
    h.proof = { data: proofWith([{}, {}]), isLoading: false, isError: false, refetch: vi.fn() };

    render(<SplitProofReceipt payment={PAYMENT} />);

    expect(screen.queryByRole('button', { name: 'Sign proof' })).toBeNull();
    expect(screen.queryByText('Nostr signature')).toBeNull();
  });

  it('hides the sign action for a payment that is not fully paid', () => {
    h.tenantOverrides = { nostr_pubkey: NOSTR_PUBKEY, nostr_npub: NOSTR_NPUB };
    h.proof = { data: proofWith([{}, {}]), isLoading: false, isError: false, refetch: vi.fn() };

    render(<SplitProofReceipt payment={{ ...PAYMENT, status: 'in_progress' }} />);

    expect(screen.queryByRole('button', { name: 'Sign proof' })).toBeNull();
  });

  it('renders the signed event instead of the sign action once signed', () => {
    h.tenantOverrides = { nostr_pubkey: NOSTR_PUBKEY, nostr_npub: NOSTR_NPUB };
    h.proof = {
      data: proofWith([{}, {}], { nostr_proof: NOSTR_PROOF }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    expect(screen.queryByRole('button', { name: 'Sign proof' })).toBeNull();
    expect(
      screen.getByText('Signed with the team’s Nostr key — verifiable with any Nostr tooling.')
    ).toBeTruthy();
    // Truncated event id and the npub it verifies against.
    expect(
      screen.getByText(`event ${NOSTR_EVENT_ID.slice(0, 18)}…${NOSTR_EVENT_ID.slice(-10)}`)
    ).toBeTruthy();
    expect(
      screen.getByText(`verifies against ${NOSTR_NPUB.slice(0, 14)}…${NOSTR_NPUB.slice(-8)}`)
    ).toBeTruthy();
  });

  it('copies the full, verbatim signed event JSON to the clipboard', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    h.proof = {
      data: proofWith([{}, {}], { nostr_proof: NOSTR_PROOF }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };

    render(<SplitProofReceipt payment={PAYMENT} />);

    fireEvent.click(screen.getByRole('button', { name: /Copy event JSON/ }));
    expect(writeText).toHaveBeenCalledWith(NOSTR_EVENT_JSON);
  });
});
