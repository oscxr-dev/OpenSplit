"""Public transparency endpoint — unauthenticated, read-only, opt-in.

Exposes a sanitised view of a tenant's split distribution and recent activity
for tenants that have explicitly opted in (``public_transparency_enabled``).

Privacy contract — this endpoint MUST NEVER expose: ln_address, payout_id,
bolt11, memo, internal IDs, API keys, store IDs, webhook secrets, emails, or
any private configuration. Only the fields assembled in ``build_public_view``
below are returned. Strictly read-only; never writes and never touches the
split engine, payout, webhook, or reconciliation logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import Payment, SplitRule, Tenant
from app.schemas import (
    PublicRecentPayment,
    PublicSplitMember,
    PublicTransparencyResponse,
)

router = APIRouter(prefix="/public", tags=["public"])

RECENT_PAYMENTS_LIMIT = 10


@dataclass
class PublicTargetRow:
    """A split target's public-safe fields (pure-function input)."""

    label: str | None
    nostr_pubkey: str | None
    percentage: float


@dataclass
class PublicPaymentRow:
    """A paid payment's public-safe fields (pure-function input)."""

    status: str
    paid_at: datetime | None
    amount_sats: int


def build_public_view(
    *,
    name: str,
    slug: str,
    show_amounts: bool,
    targets: list[PublicTargetRow],
    payments: list[PublicPaymentRow],
    total_paid_sats: int,
) -> PublicTransparencyResponse:
    """Assemble the public response, applying the show_amounts privacy gate.

    Pure and side-effect free. Only emits public-safe fields — amounts are
    suppressed entirely unless the tenant opted into showing them.
    """
    distribution = [
        PublicSplitMember(
            label=t.label,
            nostr_pubkey=t.nostr_pubkey,
            percentage=t.percentage,
        )
        for t in targets
    ]

    recent_payments = [
        PublicRecentPayment(
            status=p.status,
            paid_at=p.paid_at,
            amount_sats=(p.amount_sats if show_amounts else None),
        )
        for p in payments
    ]

    return PublicTransparencyResponse(
        name=name,
        slug=slug,
        show_amounts=show_amounts,
        distribution=distribution,
        recent_payments=recent_payments,
        total_sats=(total_paid_sats if show_amounts else None),
    )


@router.get("/{slug}", response_model=PublicTransparencyResponse)
async def public_transparency(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> PublicTransparencyResponse:
    # Opt-in only: a missing slug, a disabled page, or an inactive tenant all 404.
    tenant = (
        await session.execute(
            select(Tenant).where(
                Tenant.public_slug == slug,
                Tenant.public_transparency_enabled == True,  # noqa: E712
                Tenant.active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    active_rule = (
        await session.execute(
            select(SplitRule)
            .where(SplitRule.tenant_id == tenant.id, SplitRule.active == True)  # noqa: E712
            .options(selectinload(SplitRule.targets))
        )
    ).scalar_one_or_none()

    targets = [
        PublicTargetRow(
            label=t.label,
            nostr_pubkey=t.nostr_pubkey,
            percentage=float(t.percentage) if t.percentage is not None else 0.0,
        )
        for t in (active_rule.targets if active_rule else [])
        if float(t.percentage or 0) > 0
    ]

    paid_rows = (
        await session.execute(
            select(Payment.status, Payment.paid_at, Payment.amount_sats)
            .where(Payment.tenant_id == tenant.id, Payment.status == "paid")
            .order_by(Payment.paid_at.desc().nullslast())
            .limit(RECENT_PAYMENTS_LIMIT)
        )
    ).all()
    payments = [
        PublicPaymentRow(status=r[0], paid_at=r[1], amount_sats=int(r[2] or 0))
        for r in paid_rows
    ]

    total_paid_sats = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount_sats), 0)).where(
                Payment.tenant_id == tenant.id, Payment.status == "paid"
            )
        )
    ).scalar_one()

    return build_public_view(
        name=tenant.brand_display_name or tenant.name,
        slug=slug,
        show_amounts=tenant.public_show_amounts,
        targets=targets,
        payments=payments,
        total_paid_sats=int(total_paid_sats or 0),
    )
