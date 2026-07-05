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
from app.models import Payment, PaymentSplit, SplitRule, Tenant
from app.schemas import (
    PublicRecentPayment,
    PublicSplitRule,
    PublicSplitMember,
    PublicTeamsResponse,
    PublicTeamSummary,
    PublicTransparencyResponse,
)

router = APIRouter(prefix="/public", tags=["public"])

# Separate prefix so the discovery list doesn't collide with /public/{slug}.
public_teams_router = APIRouter(prefix="/public-teams", tags=["public"])

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


@dataclass
class PublicRuleRow:
    """A public split rule with only public-safe rule metadata."""

    name: str
    version: int
    completed_split_count: int
    targets: list[PublicTargetRow]


def build_public_view(
    *,
    name: str,
    slug: str,
    show_amounts: bool,
    targets: list[PublicTargetRow],
    payments: list[PublicPaymentRow],
    total_paid_sats: int,
    public_rules: list[PublicRuleRow] | None = None,
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
    rules = [
        PublicSplitRule(
            name=rule.name,
            version=rule.version,
            completed_split_count=rule.completed_split_count,
            distribution=[
                PublicSplitMember(
                    label=t.label,
                    nostr_pubkey=t.nostr_pubkey,
                    percentage=t.percentage,
                )
                for t in rule.targets
            ],
        )
        for rule in (public_rules or [])
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
        public_rules=rules,
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

    # Public visibility is independent from active payment routing. Only rules
    # explicitly marked public are exposed; active rules are never auto-published.
    public_rules = list(
        (
            await session.execute(
            select(SplitRule)
            .where(SplitRule.tenant_id == tenant.id, SplitRule.public_enabled == True)  # noqa: E712
            .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
            .options(selectinload(SplitRule.targets))
            )
        ).scalars().all()
    )

    completed_counts = {}
    if public_rules:
        completed_counts = dict(
            (
                await session.execute(
                    select(Payment.split_rule_id, func.count())
                    .select_from(PaymentSplit)
                    .join(Payment, Payment.id == PaymentSplit.payment_id)
                    .where(
                        Payment.tenant_id == tenant.id,
                        Payment.split_rule_id.in_([rule.id for rule in public_rules]),
                        PaymentSplit.status == "completed",
                    )
                    .group_by(Payment.split_rule_id)
                )
            ).all()
        )

    public_rule_rows = [
        PublicRuleRow(
            name=rule.name,
            version=rule.version,
            completed_split_count=int(completed_counts.get(rule.id, 0)),
            targets=[
                PublicTargetRow(
                    label=t.label,
                    nostr_pubkey=t.nostr_pubkey,
                    percentage=float(t.percentage) if t.percentage is not None else 0.0,
                )
                for t in rule.targets
                if float(t.percentage or 0) > 0
            ],
        )
        for rule in public_rules
    ]
    targets = [target for rule in public_rule_rows for target in rule.targets]

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
        # Display name is tenant.name only; brand_display_name stays dormant
        # so stale seeded branding can never resurface.
        name=tenant.name,
        slug=slug,
        show_amounts=tenant.public_show_amounts,
        targets=targets,
        public_rules=public_rule_rows,
        payments=payments,
        total_paid_sats=int(total_paid_sats or 0),
    )


@public_teams_router.get("", response_model=PublicTeamsResponse)
async def list_public_teams(
    session: AsyncSession = Depends(get_session),
) -> PublicTeamsResponse:
    """Discovery list of opt-in public teams.

    Privacy: activity METADATA only. This endpoint MUST NEVER expose money volume,
    sats, fiat, balances, ln_address, payout destinations, emails, or any private
    config. Read-only; never touches the split engine / payout / webhook logic.
    """
    tenants = (
        await session.execute(
            select(Tenant).where(
                Tenant.public_transparency_enabled == True,  # noqa: E712
                Tenant.active == True,  # noqa: E712
                Tenant.public_slug.is_not(None),
            )
        )
    ).scalars().all()
    if not tenants:
        return PublicTeamsResponse(teams=[])

    ids = [t.id for t in tenants]

    rule_counts = dict(
        (
            await session.execute(
                select(SplitRule.tenant_id, func.count())
                .where(SplitRule.tenant_id.in_(ids), SplitRule.public_enabled == True)  # noqa: E712
                .group_by(SplitRule.tenant_id)
            )
        ).all()
    )

    split_counts = dict(
        (
            await session.execute(
                select(Payment.tenant_id, func.count())
                .select_from(PaymentSplit)
                .join(Payment, Payment.id == PaymentSplit.payment_id)
                .where(Payment.tenant_id.in_(ids), PaymentSplit.status == "completed")
                .group_by(Payment.tenant_id)
            )
        ).all()
    )

    last_activity = dict(
        (
            await session.execute(
                select(Payment.tenant_id, func.max(Payment.paid_at))
                .where(Payment.tenant_id.in_(ids), Payment.status == "paid")
                .group_by(Payment.tenant_id)
            )
        ).all()
    )

    teams = [
        PublicTeamSummary(
            name=t.name,
            slug=t.public_slug or "",
            active_rule_count=int(rule_counts.get(t.id, 0)),
            completed_splits=int(split_counts.get(t.id, 0)),
            last_activity=last_activity.get(t.id),
            created_at=t.created_at,
            country=t.public_country,
            city=t.public_city,
        )
        for t in tenants
    ]
    # Default ordering: most completed splits first (privacy-safe; no money used).
    teams.sort(key=lambda team: team.completed_splits, reverse=True)
    return PublicTeamsResponse(teams=teams)
