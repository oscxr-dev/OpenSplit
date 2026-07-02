from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Boolean, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # adapter_type decides which backend processes payments: "lnbits" | "btcpay"
    adapter_type: Mapped[str] = mapped_column(String(20), nullable=False, default="btcpay")
    # LNbits fields (null for btcpay tenants)
    lnbits_admin_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    lnbits_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # BTCPay fields (null for lnbits tenants)
    btcpay_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    btcpay_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    btcpay_store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    btcpay_webhook_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    brand_logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notify_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notify_telegram_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    alert_on_failed_payout: Mapped[bool] = mapped_column(Boolean, default=True)
    # Public transparency (opt-in). Slug is the public URL key; disabled by default.
    public_slug: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    public_transparency_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Privacy P1: amounts are private by default; tenants must explicitly opt in.
    public_show_amounts: Mapped[bool] = mapped_column(Boolean, default=False)
    # Optional coarse public location for the Public Teams map (country/city level
    # only — never a precise address or coordinates). NULL => "Unknown location".
    public_country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    public_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[User]] = relationship("User", back_populates="tenant", lazy="selectin")
    split_rules: Mapped[list[SplitRule]] = relationship("SplitRule", back_populates="tenant", lazy="selectin")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | staff
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users")


# ---------------------------------------------------------------------------
# SplitRule
# ---------------------------------------------------------------------------
class SplitRule(Base):
    __tablename__ = "split_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    public_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("split_rules.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="split_rules")
    targets: Mapped[list[SplitTarget]] = relationship("SplitTarget", back_populates="rule", lazy="selectin",
                                                       order_by="SplitTarget.order")


# ---------------------------------------------------------------------------
# SplitTarget
# ---------------------------------------------------------------------------
class SplitTarget(Base):
    __tablename__ = "split_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    split_rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("split_rules.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    lnbits_wallet_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lnbits_wallet_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Lightning address for BTCPay payouts (e.g. barista@walletofsatoshi.com)
    ln_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional nostr identity for a member (npub or hex). MVP: no separate members table.
    nostr_pubkey: Mapped[str | None] = mapped_column(String(128), nullable=True)
    percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)

    rule: Mapped[SplitRule] = relationship("SplitRule", back_populates="targets")


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------
class Payment(Base):
    __tablename__ = "payments"
    # invoice_id must be unique, but it is nullable (LNbits payments may lack
    # one), so the uniqueness is partial — only where invoice_id is not null.
    __table_args__ = (
        Index(
            "uq_payments_invoice_id_not_null",
            "invoice_id",
            unique=True,
            postgresql_where=text("invoice_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(64), nullable=True)
    bolt11: Mapped[str] = mapped_column(Text, nullable=True)
    amount_sats: Mapped[int] = mapped_column(Integer, nullable=False)
    unallocated_store_sats: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    pending_remainder_sats: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    memo: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | in_progress | paid | partial | failed
    split_rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("split_rules.id"), nullable=True)
    fiat_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    fiat_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    splits: Mapped[list[PaymentSplit]] = relationship("PaymentSplit", back_populates="payment", lazy="selectin")


# ---------------------------------------------------------------------------
# PaymentSplit (audit trail)
# ---------------------------------------------------------------------------
class PaymentSplit(Base):
    __tablename__ = "payment_splits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), nullable=False)
    split_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("split_targets.id"), nullable=False)
    amount_sats: Mapped[int] = mapped_column(Integer, nullable=False)
    btcpay_payout_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payment: Mapped[Payment] = relationship("Payment", back_populates="splits")
    split_target: Mapped[SplitTarget | None] = relationship("SplitTarget", lazy="selectin")
