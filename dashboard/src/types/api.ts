export interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TenantResponse {
  id: string;
  name: string;
  adapter_type: 'lnbits' | 'btcpay';
  lnbits_url: string | null;
  brand_display_name: string | null;
  brand_color: string | null;
  brand_logo_url: string | null;
  public_slug?: string | null;
  public_show_amounts?: boolean | null;
  active: boolean;
  created_at: string;
}

export interface TenantHealth {
  tenant: TenantResponse;
  lnbits_status: string;
}

export interface SplitTarget {
  id?: string;
  label: string;
  lnbits_wallet_id?: string | null;
  lnbits_wallet_name?: string | null;
  ln_address?: string | null;
  percentage: number;
  order: number;
  /** True when a dynamic LND receiver is configured for this label; such a
   *  target is valid without a Lightning address. */
  has_lnd_receiver?: boolean;
}

export interface SplitRule {
  id: string;
  name: string;
  active: boolean;
  version: number;
  parent_rule_id: string | null;
  targets: SplitTarget[];
  created_at: string;
  can_delete: boolean;
}

export interface SplitRuleCreate {
  name: string;
  targets: Omit<SplitTarget, 'id'>[];
}

export interface SplitRuleUpdate {
  name?: string;
  targets?: Omit<SplitTarget, 'id'>[];
}

export interface PaymentSplit {
  id: string;
  label: string | null;
  ln_address: string | null;
  amount_sats: number;
  status: string;
  payout_id: string | null;
  failure_reason: string | null;
  retry_count: number;
  last_checked_at: string | null;
  executed_at: string;
}

export interface Invoice {
  id: string;
  bolt11: string | null;
  amount_sats: number;
  fiat_amount: number | null;
  fiat_currency: string | null;
  memo: string | null;
  status: string;
  paid_at: string | null;
  splits: PaymentSplit[];
  created_at: string;
}

export interface InvoiceCreateRequest {
  amount_sats: number;
  memo?: string;
}

export interface WalletBalance {
  label: string;
  lnbits_wallet_id: string;
  lnbits_wallet_name: string | null;
  percentage: number;
  accumulated_sats: number;
  current_balance_sats: number | null;
  color_index: number;
}

export interface InvoiceListResponse {
  items: Invoice[];
  total: number;
}

// ── Members (GET /members) ────────────────────────────────────────────────
export interface Member {
  label: string;
  ln_address: string | null;
  nostr_pubkey: string | null;
  current_percentage: number | null;
  total_paid_sats: number;
  payment_count: number;
  last_payment_at: string | null;
  failed_count: number;
  target_count: number;
  collision: boolean;
}

// ── Split proof (GET /payments/{id}/proof) ────────────────────────────────
export interface ProofSplit {
  split_id: string;
  split_target_id: string | null;
  label: string | null;
  ln_address: string | null;
  nostr_pubkey: string | null;
  percentage: number | null;
  amount_sats: number;
  payout_status: string;
  payout_id: string | null;
}

export interface ProofIntegrity {
  payment_amount_sats: number;
  split_sum_sats: number;
  difference_sats: number;
  balanced: boolean;
}

export interface SplitProof {
  payment_id: string;
  amount_sats: number;
  status: string;
  split_rule_id: string | null;
  split_rule_version: number | null;
  members: ProofSplit[];
  integrity: ProofIntegrity;
}

// ── Public transparency (GET /public/{slug}) — no private data ─────────────
export interface PublicSplitMember {
  label: string | null;
  nostr_pubkey: string | null;
  percentage: number;
}

export interface PublicRecentPayment {
  status: string;
  paid_at: string | null;
  amount_sats: number | null;
}

export interface PublicTransparency {
  name: string;
  slug: string;
  show_amounts: boolean;
  distribution: PublicSplitMember[];
  recent_payments: PublicRecentPayment[];
  total_sats: number | null;
}

export interface DashboardSummary {
  liquidity: {
    local_sat: number | null;
    remote_sat: number | null;
    can_send_sat: number | null;
    can_receive_sat: number | null;
    status: 'green' | 'amber' | 'red' | 'unavailable';
  };
  today: {
    count: number;
    total_sats: number;
    total_fiat: number | null;
    fiat_currency: string | null;
  };
  failed_count: number;
  recent_payments: Array<{
    id: string;
    amount_sats: number;
    fiat_amount: number | null;
    fiat_currency: string | null;
    status: string;
    paid_at: string | null;
    splits_summary: string;
  }>;
}
