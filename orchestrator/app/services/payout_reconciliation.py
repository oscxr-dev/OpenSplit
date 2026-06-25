from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models import Payment, PaymentSplit, Tenant
from app.services.btcpay_client import BTCPayClient
from app.services.split_engine import derive_payment_status

logger = structlog.get_logger(__name__)

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
BTCPAY_STATUS_MAP = {
    "AwaitingApproval": "in_progress",
    "AwaitingPayment": "in_progress",
    "InProgress": "in_progress",
    "Completed": "completed",
    "Cancelled": "failed",
}


def map_btcpay_payout_state(state: str | None) -> str:
    return BTCPAY_STATUS_MAP.get(state or "", "in_progress")


def payout_failure_reason(payout: dict, state: str | None) -> str:
    payment_proof = payout.get("paymentProof")
    metadata = payout.get("metadata")
    if isinstance(payment_proof, dict) and payment_proof.get("error"):
        return str(payment_proof["error"])
    if isinstance(metadata, dict) and metadata.get("error"):
        return str(metadata["error"])
    return f"BTCPay reportó el payout como {state or 'Cancelled'}."


async def reconcile_tenant_payouts(session: AsyncSession, tenant: Tenant) -> int:
    result = await session.execute(
        select(PaymentSplit)
        .join(Payment, Payment.id == PaymentSplit.payment_id)
        .where(
            Payment.tenant_id == tenant.id,
            PaymentSplit.btcpay_payout_id.is_not(None),
            PaymentSplit.status.not_in(TERMINAL_STATUSES),
        )
        .options(selectinload(PaymentSplit.split_target))
    )
    splits = list(result.scalars().all())
    if not splits:
        return 0

    client = BTCPayClient(
        base_url=tenant.btcpay_url or "",
        api_key=tenant.btcpay_api_key or "",
        store_id=tenant.btcpay_store_id or "",
    )
    changed = 0
    try:
        for split in splits:
            try:
                payout = await client.get_payout(split.btcpay_payout_id or "")
                state = payout.get("state")
                next_status = map_btcpay_payout_state(state)
                if next_status != split.status:
                    changed += 1
                split.status = next_status
                split.last_checked_at = datetime.now(timezone.utc)
                if next_status == "failed":
                    split.failure_reason = payout_failure_reason(payout, state)
                elif next_status == "completed":
                    split.failure_reason = None
            except Exception as exc:
                split.last_checked_at = datetime.now(timezone.utc)
                logger.warning(
                    "payout_reconciliation_check_failed",
                    payout_id=split.btcpay_payout_id,
                    error=str(exc),
                )

        # Re-derive each touched payment's status from its full set of splits.
        for payment_id in {split.payment_id for split in splits}:
            payment = (
                await session.execute(
                    select(Payment)
                    .where(Payment.id == payment_id)
                    .options(selectinload(Payment.splits))
                )
            ).scalar_one()
            payment.status = derive_payment_status(payment.splits)

        await session.commit()
    finally:
        await client.close()
    return changed


async def reconcile_all_payouts() -> int:
    async with async_session() as session:
        result = await session.execute(
            select(Tenant).where(
                Tenant.active.is_(True),
                Tenant.adapter_type == "btcpay",
                Tenant.btcpay_url.is_not(None),
                Tenant.btcpay_api_key.is_not(None),
                Tenant.btcpay_store_id.is_not(None),
            )
        )
        tenants = list(result.scalars().all())
        changed = 0
        for tenant in tenants:
            changed += await reconcile_tenant_payouts(session, tenant)
        return changed


async def payout_reconciliation_loop(interval_seconds: int) -> None:
    while True:
        try:
            changed = await reconcile_all_payouts()
            if changed:
                logger.info("payout_reconciliation_complete", changed=changed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("payout_reconciliation_failed", error=str(exc))
        await asyncio.sleep(interval_seconds)
