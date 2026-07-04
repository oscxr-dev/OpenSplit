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
  public_transparency_enabled?: boolean | null;
  public_country?: string | null;
  public_city?: string | null;
  /** BTCPay connection. The raw API key and webhook secret are never sent by
   *  the server — only presence indicators (`btcpay_api_key_set` /
   *  `btcpay_api_key_last4` / `btcpay_webhook_secret_set`). */
  btcpay_url?: string | null;
  btcpay_store_id?: string | null;
  btcpay_api_key_set?: boolean;
  btcpay_api_key_last4?: string | null;
  btcpay_webhook_secret_set?: boolean;
  /** Timestamp of the last signature-valid BTCPay webhook; null until the
   *  first one lands (or after the secret is regenerated). */
  last_webhook_at?: string | null;
  active: boolean;
  created_at: string;
}

/** Privacy-safe public team summary for the Public Teams discovery page. */
export interface PublicTeamSummary {
  name: string;
  slug: string;
  active_rule_count: number;
  completed_splits: number;
  last_activity: string | null;
  created_at: string;
  country: string | null;
  city: string | null;
}

export interface TenantHealth {
  tenant: TenantResponse;
  /** Current adapter connection status ("ok" | "unreachable"). */
  connection_status: string;
  /** Legacy alias of connection_status; do not use in new code. */
  lnbits_status: string;
}

/** Granular result of POST /tenants/me/btcpay/test. `auth_ok` / `store_found`
 *  are null when an earlier check already failed (never evaluated). */
export interface BtcPayConnectionTest {
  url_reachable: boolean;
  auth_ok: boolean | null;
  store_found: boolean | null;
  ok: boolean;
  detail: string;
}

export interface BtcPayAuthorizeUrl {
  authorize_url: string;
  permissions: string[];
}

/** One-time reveal from POST /tenants/me/btcpay/webhook-secret — the only
 *  response that ever carries the raw webhook secret. */
export interface BtcPayWebhookSecret {
  secret: string;
  webhook_url: string;
  events: string[];
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
  public_enabled: boolean;
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
  /** BTCPay's raw payout state ("AwaitingPayment", ...) from the last
   *  reconciliation check; null until the first check lands. */
  btcpay_payout_state?: string | null;
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
  /** Raw BTCPay payout state from the last reconciliation check. */
  btcpay_payout_state?: string | null;
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

export interface PublicSplitRule {
  name: string;
  version: number;
  completed_split_count: number;
  distribution: PublicSplitMember[];
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
  public_rules: PublicSplitRule[];
  distribution: PublicSplitMember[];
  recent_payments: PublicRecentPayment[];
  total_sats: number | null;
}

// ── Aggregate pipeline status (GET /tenants/me/status) ─────────────────────
export interface TenantStatus {
  store: 'not_configured' | 'unreachable' | 'ok';
  webhook: 'not_configured' | 'waiting' | 'verified';
  active_rule: { name: string; version: number } | null;
  payout_delivery: 'idle' | 'delivering' | 'waiting_in_btcpay' | 'failing';
  public_page: 'off' | 'on';
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
