"""Members endpoint — MVP.

There is no members table yet. A "member" is derived from the tenant's active,
non-zero split targets and enriched with payout history for matching historical
targets. Read-only; never writes and never touches payout, split, or
reconciliation logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget, Tenant, User
from app.schemas import MemberResponse

router = APIRouter(prefix="/members", tags=["members"])


@dataclass
class MemberTargetRow:
    """One split_target plus its derived payout stats (pure-function input)."""

    label: str
    ln_address: str | None
    nostr_pubkey: str | None
    percentage: float | None
    is_active: bool  # target belongs to the tenant's currently active rule
    paid_sats: int = 0
    payment_count: int = 0
    failed_count: int = 0
    last_payment_at: datetime | None = None


def member_key(label: str, ln_address: str | None) -> str:
    """Aggregation key for the UI's active split targets.

    The label is part of the key so two split targets can intentionally pay the
    same Lightning address while still appearing as distinct partners.
    """
    clean_label = label.strip().lower()
    if ln_address and ln_address.strip():
        return f"label:{clean_label}|addr:{ln_address.strip().lower()}"
    return f"label:{clean_label}"


def build_members(rows: list[MemberTargetRow]) -> list[MemberResponse]:
    """Collapse split_target rows into members. Pure and side-effect free."""
    groups: dict[str, list[MemberTargetRow]] = {}
    for row in rows:
        groups.setdefault(member_key(row.label, row.ln_address), []).append(row)

    members: list[MemberResponse] = []
    for group in groups.values():
        active_rows = [r for r in group if r.is_active]
        rep = active_rows[0] if active_rows else group[0]

        labels = {r.label.strip().lower() for r in group if r.label}
        addrs = {r.ln_address.strip().lower() for r in group if r.ln_address and r.ln_address.strip()}
        nostrs = {r.nostr_pubkey for r in group if r.nostr_pubkey}
        collision = len(labels) > 1 or len(addrs) > 1 or len(nostrs) > 1

        dates = [r.last_payment_at for r in group if r.last_payment_at is not None]

        members.append(
            MemberResponse(
                label=rep.label,
                ln_address=rep.ln_address,
                nostr_pubkey=rep.nostr_pubkey or next(iter(nostrs), None),
                current_percentage=active_rows[0].percentage if active_rows else None,
                total_paid_sats=sum(r.paid_sats for r in group),
                payment_count=sum(r.payment_count for r in group),
                last_payment_at=max(dates) if dates else None,
                failed_count=sum(r.failed_count for r in group),
                target_count=len(group),
                collision=collision,
            )
        )

    members.sort(key=lambda m: (-m.total_paid_sats, m.label.lower()))
    return members


@router.get("", response_model=list[MemberResponse])
async def list_members(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[MemberResponse]:
    active_rule_id = (
        await session.execute(
            select(SplitRule.id).where(
                SplitRule.tenant_id == tenant.id, SplitRule.active == True  # noqa: E712
            )
        )
    ).scalar_one_or_none()

    # All split_targets for this tenant so current targets can retain matching
    # historical payout stats without surfacing inactive/zero-percent partners.
    target_rows = (
        await session.execute(
            select(SplitTarget, SplitRule.id.label("rule_id"))
            .join(SplitRule, SplitRule.id == SplitTarget.split_rule_id)
            .where(SplitRule.tenant_id == tenant.id)
        )
    ).all()

    active_member_keys = {
        member_key(target.label, target.ln_address)
        for target, rule_id in target_rows
        if rule_id == active_rule_id and float(target.percentage or 0) > 0
    }
    if not active_member_keys:
        return []

    # Per-target payout aggregation, scoped to this tenant's payments.
    stats_rows = (
        await session.execute(
            select(
                PaymentSplit.split_target_id,
                func.coalesce(
                    func.sum(
                        case((PaymentSplit.status == "completed", PaymentSplit.amount_sats), else_=0)
                    ),
                    0,
                ),
                func.count(func.distinct(PaymentSplit.payment_id)),
                func.max(Payment.paid_at),
                func.coalesce(
                    func.sum(case((PaymentSplit.status == "failed", 1), else_=0)), 0
                ),
            )
            .join(Payment, Payment.id == PaymentSplit.payment_id)
            .where(Payment.tenant_id == tenant.id)
            .group_by(PaymentSplit.split_target_id)
        )
    ).all()
    stats = {row[0]: (row[1], row[2], row[3], row[4]) for row in stats_rows}

    rows: list[MemberTargetRow] = []
    for target, rule_id in target_rows:
        if member_key(target.label, target.ln_address) not in active_member_keys:
            continue
        paid_sats, payment_count, last_payment_at, failed_count = stats.get(
            target.id, (0, 0, None, 0)
        )
        rows.append(
            MemberTargetRow(
                label=target.label,
                ln_address=target.ln_address,
                nostr_pubkey=target.nostr_pubkey,
                percentage=float(target.percentage) if target.percentage is not None else None,
                is_active=(rule_id == active_rule_id),
                paid_sats=int(paid_sats or 0),
                payment_count=int(payment_count or 0),
                last_payment_at=last_payment_at,
                failed_count=int(failed_count or 0),
            )
        )

    return build_members(rows)
