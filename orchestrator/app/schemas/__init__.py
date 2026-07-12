from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.percentages import quantized_total


# ── Auth ──────────────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


# ── Tenant ────────────────────────────────────────────────────────────────
class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    adapter_type: str
    lnbits_url: str | None = None
    brand_display_name: str | None = None
    brand_color: str | None = None
    brand_logo_url: str | None = None
    public_slug: str | None = None
    public_transparency_enabled: bool = False
    # Per-tenant display preference, NOT a secret — safe to expose so the UI can
    # reflect the saved toggle. Amounts stay private by default (Privacy P1).
    public_show_amounts: bool = False
    public_country: str | None = None
    public_city: str | None = None
    # Team Nostr identity — PUBLIC key only (x-only hex + derived npub display).
    # The signing key is env-held server config and has no schema anywhere.
    nostr_pubkey: str | None = None
    nostr_npub: str | None = None
    # BTCPay connection — REDACTION CONTRACT: the raw btcpay_api_key and
    # btcpay_webhook_secret must NEVER be fields on this (or any) response
    # schema. Only presence indicators leave the server. (The sole exception is
    # BTCPayWebhookSecret: the one-time reveal at generation time.)
    btcpay_url: str | None = None
    btcpay_store_id: str | None = None
    btcpay_api_key_set: bool = False
    btcpay_api_key_last4: str | None = None
    btcpay_webhook_secret_set: bool = False
    last_webhook_at: datetime | None = None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


def _normalize_slug(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"['’]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


class TenantUpdate(BaseModel):
    name: str | None = None
    lnbits_url: str | None = None
    public_slug: str | None = None
    public_transparency_enabled: bool | None = None
    public_show_amounts: bool | None = None
    public_country: str | None = None
    public_city: str | None = None
    btcpay_url: str | None = None
    btcpay_api_key: str | None = None
    btcpay_store_id: str | None = None
    # Nostr PUBLIC key (npub or 64-hex; normalized to hex). Unlike the BTCPay
    # fields, an explicitly provided blank CLEARS the stored key (the router
    # checks model_fields_set) — removing a verification identity is a
    # legitimate, safe operation. An nsec is rejected with a loud error.
    nostr_pubkey: str | None = None

    @field_validator("nostr_pubkey")
    @classmethod
    def normalize_nostr_pubkey_field(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from app.core.nostr_keys import normalize_nostr_pubkey

        return normalize_nostr_pubkey(value)

    @field_validator("btcpay_url")
    @classmethod
    def normalize_btcpay_url(cls, value: str | None) -> str | None:
        # Stored without a trailing slash. Blank means "not provided" — PATCH
        # semantics: it must never wipe a stored value, same as omitting it.
        if value is None:
            return None
        trimmed = value.strip().rstrip("/")
        if not trimmed:
            return None
        if not trimmed.lower().startswith(("http://", "https://")):
            raise ValueError("BTCPay server URL must start with http:// or https://")
        # Guard against truncated hosts like "http://h": require a hostname
        # with at least one dot, or localhost / host.docker.internal. Mirrors
        # the dashboard rule in dashboard/src/lib/browserUrl.ts.
        try:
            hostname = (urlsplit(trimmed).hostname or "").lower()
        except ValueError:
            raise ValueError("BTCPay server URL is not a valid URL")
        if hostname not in ("localhost", "host.docker.internal") and "." not in hostname:
            raise ValueError(
                "BTCPay server URL needs a full hostname "
                "(e.g. btcpay.example.com, localhost, or host.docker.internal)"
            )
        return trimmed

    @field_validator("btcpay_api_key", "btcpay_store_id")
    @classmethod
    def trim_btcpay_credential(cls, value: str | None) -> str | None:
        # Trim; blank means "not provided" and never wipes a stored value.
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("btcpay_store_id")
    @classmethod
    def limit_store_id_length(cls, value: str | None) -> str | None:
        # Column is String(64); reject early instead of failing at the DB.
        if value is not None and len(value) > 64:
            raise ValueError("BTCPay store ID must be 64 characters or fewer")
        return value

    @field_validator("public_slug")
    @classmethod
    def normalize_public_slug(cls, value: str | None) -> str | None:
        # Slugs must be lowercase, URL-safe, no spaces. Normalize defensively so
        # the saved value is always a valid public route (e.g. "Oscar Shop's" ->
        # "oscar-shops"). None means "not provided" and is left untouched.
        if value is None:
            return None
        slug = _normalize_slug(value)
        if not slug:
            raise ValueError("Public URL slug must contain letters or numbers")
        return slug

    @field_validator("public_country", "public_city")
    @classmethod
    def trim_location(cls, value: str | None) -> str | None:
        # Coarse, optional location labels. Trim; blank becomes None ("Unknown").
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class TenantHealth(BaseModel):
    tenant: TenantResponse
    # Current adapter connection status ("ok" | "unreachable").
    connection_status: str
    # Legacy name carrying the same value; kept for wire compatibility.
    lnbits_status: str


class BTCPayConnectionTest(BaseModel):
    """Granular result of the read-only BTCPay connection probe.

    ``auth_ok`` / ``store_found`` are None when an earlier step already failed
    (never evaluated). ``detail`` is one actionable sentence and must never
    contain credentials.
    """

    url_reachable: bool
    auth_ok: bool | None = None
    store_found: bool | None = None
    ok: bool
    detail: str


class BTCPayAuthorizeUrl(BaseModel):
    authorize_url: str
    permissions: list[str]


class TenantStatusActiveRule(BaseModel):
    name: str
    version: int


class TenantStatusResponse(BaseModel):
    """Aggregate pipeline health for the dashboard's status strip.

    Read-only snapshot: is the store reachable, is the webhook verified, which
    rule is active, are payouts flowing, and is the public page on.
    """

    store: str  # "not_configured" | "unreachable" | "ok"
    webhook: str  # "not_configured" | "waiting" | "verified"
    active_rule: TenantStatusActiveRule | None = None
    payout_delivery: str  # "idle" | "delivering" | "waiting_in_btcpay" | "failing"
    # Whether a Lightning payout processor is configured in BTCPay to auto-send
    # payouts. Only probed when store == "ok"; "unknown" when the key can't read
    # processors or the store isn't reachable.
    lightning_payout_processor: str = "unknown"  # "active" | "missing" | "unknown"
    public_page: str  # "off" | "on"


class BTCPayWebhookSecret(BaseModel):
    """One-time reveal of a freshly generated webhook secret.

    The ONLY response that ever carries the raw secret — every other endpoint
    is bound by the redaction contract (``btcpay_webhook_secret_set`` /
    ``last_webhook_at`` are the only readable traces).
    """

    secret: str
    webhook_url: str
    events: list[str]


# ── Split Rules ───────────────────────────────────────────────────────────
class SplitTargetSchema(BaseModel):
    id: uuid.UUID | None = None
    label: str
    lnbits_wallet_id: str | None = None
    lnbits_wallet_name: str | None = None
    ln_address: str | None = None
    percentage: float
    order: int = 0
    # True when a dynamic LND receiver is configured for this target's label.
    # Such targets don't require a Lightning address.
    has_lnd_receiver: bool = False

    model_config = {"from_attributes": True}


class SplitRuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    public_enabled: bool = False
    version: int
    parent_rule_id: uuid.UUID | None = None
    targets: list[SplitTargetSchema]
    created_at: datetime
    can_delete: bool = False

    model_config = {"from_attributes": True}


class SplitTargetCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    lnbits_wallet_id: str | None = Field(default=None, max_length=64)
    lnbits_wallet_name: str | None = Field(default=None, max_length=100)
    ln_address: str | None = Field(default=None, max_length=255)
    percentage: float = Field(gt=0, le=100)
    order: int = Field(default=0, ge=0)

    @field_validator("label")
    @classmethod
    def strip_required_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Target label is required")
        return value

    @field_validator("lnbits_wallet_id", "lnbits_wallet_name", "ln_address", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class SplitRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    targets: list[SplitTargetCreate] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def strip_required_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Split rule name is required")
        return value

    @model_validator(mode="after")
    def validate_total(self) -> SplitRuleCreate:
        # Partial split rules are allowed: targets may total anywhere in (0, 100].
        # Any unallocated remainder simply stays in the store. Over-allocation
        # (> 100%) is rejected.
        total = quantized_total(t.percentage for t in self.targets)
        if total <= Decimal("0") or total > Decimal("100"):
            raise ValueError(f"Target percentages must total >0 and <=100%, got {total}%")
        return self


class SplitRuleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    targets: list[SplitTargetCreate] | None = None

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Split rule name is required")
        return value

    @model_validator(mode="after")
    def validate_total_if_targets(self) -> SplitRuleUpdate:
        # Partial split rules allowed: total may be in (0, 100]. Reject > 100%.
        if self.targets is not None:
            total = quantized_total(t.percentage for t in self.targets)
            if total <= Decimal("0") or total > Decimal("100"):
                raise ValueError(f"Target percentages must total >0 and <=100%, got {total}%")
        return self


class SplitRulePublicUpdate(BaseModel):
    public_enabled: bool


# ── Invoices ──────────────────────────────────────────────────────────────
class InvoiceCreateRequest(BaseModel):
    amount_sats: int = Field(gt=0)
    memo: str | None = None


class PaymentSplitResponse(BaseModel):
    id: uuid.UUID
    label: str | None = None
    ln_address: str | None = None
    amount_sats: int
    status: str
    # BTCPay's raw payout state ("AwaitingPayment", ...) from the last
    # reconciliation check; None until the first check lands.
    btcpay_payout_state: str | None = None
    # Lightning settlement proof recorded when the payout completed —
    # sha256(ln_preimage) == ln_payment_hash. Verbatim from BTCPay; None for
    # on-chain/failed/pre-existing payouts. Authenticated responses only.
    ln_preimage: str | None = None
    ln_payment_hash: str | None = None
    payout_id: str | None = None
    failure_reason: str | None = None
    retry_count: int = 0
    last_checked_at: datetime | None = None
    executed_at: datetime

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    bolt11: str | None = None
    amount_sats: int
    fiat_amount: Decimal | None = None
    fiat_currency: str | None = None
    memo: str | None = None
    status: str
    paid_at: datetime | None = None
    splits: list[PaymentSplitResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    total: int


# ── Merchant Dashboard ───────────────────────────────────────────────────
class LiquiditySummary(BaseModel):
    local_sat: int | None = None
    remote_sat: int | None = None
    can_send_sat: int | None = None
    can_receive_sat: int | None = None
    status: str = "unavailable"


class TodaySummary(BaseModel):
    count: int
    total_sats: int
    total_fiat: Decimal | None = None
    fiat_currency: str | None = None


class RecentPaymentResponse(BaseModel):
    id: uuid.UUID
    amount_sats: int
    fiat_amount: Decimal | None = None
    fiat_currency: str | None = None
    status: str
    paid_at: datetime | None = None
    splits_summary: str


class DashboardSummaryResponse(BaseModel):
    liquidity: LiquiditySummary
    today: TodaySummary
    failed_count: int
    recent_payments: list[RecentPaymentResponse]


# ── Members (derived from split_targets; MVP, no members table) ────────────
class MemberResponse(BaseModel):
    label: str
    ln_address: str | None = None
    nostr_pubkey: str | None = None
    current_percentage: float | None = None  # from the tenant's active rule, if present
    total_paid_sats: int = 0
    payment_count: int = 0
    last_payment_at: datetime | None = None
    failed_count: int = 0
    target_count: int = 1  # how many split_targets collapsed into this member
    collision: bool = False  # ambiguous merge (same key, differing label/address/nostr)


# ── Split proof (read-only audit of how one payment was split) ─────────────
class ProofSplitResponse(BaseModel):
    split_id: uuid.UUID
    split_target_id: uuid.UUID | None = None
    label: str | None = None
    ln_address: str | None = None
    nostr_pubkey: str | None = None
    percentage: float | None = None
    amount_sats: int
    payout_status: str
    # Raw BTCPay payout state from the last reconciliation check (see
    # PaymentSplitResponse.btcpay_payout_state).
    btcpay_payout_state: str | None = None
    payout_id: str | None = None  # internal/private endpoint only
    # Lightning settlement proof (see PaymentSplitResponse.ln_preimage).
    # Authenticated proof only — never exposed on public pages.
    ln_preimage: str | None = None
    ln_payment_hash: str | None = None


class ProofIntegrity(BaseModel):
    payment_amount_sats: int
    split_sum_sats: int
    unallocated_store_sats: int = 0
    pending_remainder_sats: int = 0
    difference_sats: int  # payment_amount_sats - split_sum_sats - store - pending
    balanced: bool  # True when split amounts + store remainder + pending remainder sum exactly to payment


class NostrProofResponse(BaseModel):
    """A stored team-signed Nostr proof event, plus parsed display fields.

    ``event_json`` is the verbatim signed event exactly as persisted — the
    copyable artifact third parties verify. The other fields are parsed out
    of it server-side purely for display (never re-derived from key material).
    """

    event_json: str
    event_id: str
    pubkey: str
    npub: str
    kind: int
    created_at: int


class SplitProofResponse(BaseModel):
    payment_id: uuid.UUID
    amount_sats: int
    status: str  # payment status
    split_rule_id: uuid.UUID | None = None
    split_rule_version: int | None = None
    # Hex SHA-256 of the frozen rule's canonical form (services/proof_hash.py),
    # captured at payment freeze time. Authenticated proof only for now — see
    # the EXPOSURE note in proof_hash.py before adding it to public pages.
    rule_fingerprint: str | None = None
    # Team-signed Nostr event over this proof (services/nostr_proof.py).
    # Authenticated proof only — public-page exposure is a separate decision.
    nostr_proof: NostrProofResponse | None = None
    members: list[ProofSplitResponse]
    integrity: ProofIntegrity


# ── Public transparency (opt-in, unauthenticated, no private data) ─────────
class PublicSplitMember(BaseModel):
    # Public identity only — never an ln_address or internal id.
    label: str | None = None
    nostr_pubkey: str | None = None
    percentage: float


class PublicSplitRule(BaseModel):
    name: str
    version: int
    completed_split_count: int = 0
    distribution: list[PublicSplitMember]


class PublicRecentPayment(BaseModel):
    status: str
    paid_at: datetime | None = None
    amount_sats: int | None = None  # populated only when show_amounts is true


class PublicTransparencyResponse(BaseModel):
    name: str  # workspace/project display name
    slug: str
    show_amounts: bool
    public_rules: list[PublicSplitRule] = Field(default_factory=list)
    distribution: list[PublicSplitMember]
    recent_payments: list[PublicRecentPayment]
    total_sats: int | None = None  # populated only when show_amounts is true


# ── Public Teams discovery (opt-in, unauthenticated) ───────────────────────
# Privacy: activity METADATA only. Never money volume / sats / fiat / balances,
# never ln_address, payout destinations, emails, or private config.
class PublicTeamSummary(BaseModel):
    name: str
    slug: str
    active_rule_count: int
    completed_splits: int
    last_activity: datetime | None = None
    created_at: datetime
    country: str | None = None
    city: str | None = None


class PublicTeamsResponse(BaseModel):
    teams: list[PublicTeamSummary]


# ── Webhook ───────────────────────────────────────────────────────────────
class LNBitsWebhookPayload(BaseModel):
    payment_hash: str
    payment_request: str | None = None
    amount: int = 0  # msats
    memo: str | None = None
    checking_id: str | None = None


# ── Health ────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    db: str  # "ok" | "error"
    lnbits: str  # "ok" | "error" | "skipped" (skipped when LNBits is not enabled)
