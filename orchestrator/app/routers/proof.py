"""Split proof endpoint — read-only.

Returns a clear, auditable proof of how a single payment was split across its
members/targets, including a sanity integrity check that the split amounts sum
to the payment amount.

Strictly read-only: never writes, and never touches the split engine, payout,
webhook, or reconciliation logic. Tenant-scoped — a payment is only visible to
the tenant that owns it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget, Tenant, User
from app.schemas import ProofIntegrity, ProofSplitResponse, SplitProofResponse

router = APIRouter(prefix="/payments", tags=["proof"])


@dataclass
class ProofSplitRow:
    """One payment_split plus its target details (pure-function input)."""

    split_id: uuid.UUID
    split_target_id: uuid.UUID | None
    label: str | None
    ln_address: str | None
    nostr_pubkey: str | None
    percentage: float | None
    amount_sats: int
    payout_status: str
    payout_id: str | None


def build_proof(
    *,
    payment_id: uuid.UUID,
    amount_sats: int,
    unallocated_store_sats: int = 0,
    pending_remainder_sats: int = 0,
    status: str,
    split_rule_id: uuid.UUID | None,
    split_rule_version: int | None,
    rows: list[ProofSplitRow],
) -> SplitProofResponse:
    """Assemble the proof payload and integrity check. Pure and side-effect free."""
    members = [
        ProofSplitResponse(
            split_id=row.split_id,
            split_target_id=row.split_target_id,
            label=row.label,
            ln_address=row.ln_address,
            nostr_pubkey=row.nostr_pubkey,
            percentage=row.percentage,
            amount_sats=row.amount_sats,
            payout_status=row.payout_status,
            payout_id=row.payout_id,
        )
        for row in rows
    ]

    split_sum = sum(row.amount_sats for row in rows)
    difference_sats = amount_sats - split_sum - unallocated_store_sats - pending_remainder_sats
    integrity = ProofIntegrity(
        payment_amount_sats=amount_sats,
        split_sum_sats=split_sum,
        unallocated_store_sats=unallocated_store_sats,
        pending_remainder_sats=pending_remainder_sats,
        difference_sats=difference_sats,
        balanced=(difference_sats == 0),
    )

    return SplitProofResponse(
        payment_id=payment_id,
        amount_sats=amount_sats,
        status=status,
        split_rule_id=split_rule_id,
        split_rule_version=split_rule_version,
        members=members,
        integrity=integrity,
    )


@router.get("/{payment_id}/proof", response_model=SplitProofResponse)
async def get_split_proof(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> SplitProofResponse:
    result = await session.execute(
        select(Payment)
        .where(Payment.id == payment_id, Payment.tenant_id == tenant.id)
        .options(
            selectinload(Payment.splits).selectinload(PaymentSplit.split_target)
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    split_rule_version: int | None = None
    if payment.split_rule_id is not None:
        split_rule_version = (
            await session.execute(
                select(SplitRule.version).where(
                    SplitRule.id == payment.split_rule_id,
                    SplitRule.tenant_id == tenant.id,
                )
            )
        ).scalar_one_or_none()

    rows: list[ProofSplitRow] = []
    for split in payment.splits:
        target: SplitTarget | None = split.split_target
        rows.append(
            ProofSplitRow(
                split_id=split.id,
                split_target_id=split.split_target_id,
                label=target.label if target else None,
                ln_address=target.ln_address if target else None,
                nostr_pubkey=target.nostr_pubkey if target else None,
                percentage=float(target.percentage)
                if target and target.percentage is not None
                else None,
                amount_sats=split.amount_sats,
                payout_status=split.status,
                payout_id=split.btcpay_payout_id,
            )
        )

    return build_proof(
        payment_id=payment.id,
        amount_sats=payment.amount_sats,
        unallocated_store_sats=payment.unallocated_store_sats,
        pending_remainder_sats=payment.pending_remainder_sats,
        status=payment.status,
        split_rule_id=payment.split_rule_id,
        split_rule_version=split_rule_version,
        rows=rows,
    )
