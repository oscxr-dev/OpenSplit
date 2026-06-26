from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

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
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantUpdate(BaseModel):
    name: str | None = None
    lnbits_url: str | None = None


class TenantHealth(BaseModel):
    tenant: TenantResponse
    lnbits_status: str  # compatibility field: current adapter connection status


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
    def validate_100(self) -> SplitRuleCreate:
        total = quantized_total(t.percentage for t in self.targets)
        if total != Decimal("100"):
            raise ValueError(f"Target percentages must sum to 100%, got {total}%")
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
    def validate_100_if_targets(self) -> SplitRuleUpdate:
        if self.targets is not None:
            total = quantized_total(t.percentage for t in self.targets)
            if total != Decimal("100"):
                raise ValueError(f"Target percentages must sum to 100%, got {total}%")
        return self


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
    payout_id: str | None = None  # internal/private endpoint only


class ProofIntegrity(BaseModel):
    payment_amount_sats: int
    split_sum_sats: int
    difference_sats: int  # payment_amount_sats - split_sum_sats
    balanced: bool  # True when split amounts sum exactly to the payment amount


class SplitProofResponse(BaseModel):
    payment_id: uuid.UUID
    amount_sats: int
    status: str  # payment status
    split_rule_id: uuid.UUID | None = None
    split_rule_version: int | None = None
    members: list[ProofSplitResponse]
    integrity: ProofIntegrity


# ── Public transparency (opt-in, unauthenticated, no private data) ─────────
class PublicSplitMember(BaseModel):
    # Public identity only — never an ln_address or internal id.
    label: str | None = None
    nostr_pubkey: str | None = None
    percentage: float


class PublicRecentPayment(BaseModel):
    status: str
    paid_at: datetime | None = None
    amount_sats: int | None = None  # populated only when show_amounts is true


class PublicTransparencyResponse(BaseModel):
    name: str  # workspace/project display name
    slug: str
    show_amounts: bool
    distribution: list[PublicSplitMember]
    recent_payments: list[PublicRecentPayment]
    total_sats: int | None = None  # populated only when show_amounts is true


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
