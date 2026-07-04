from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Payment, PaymentSplit, Tenant, User
from app.schemas import InvoiceListResponse, InvoiceResponse, PaymentSplitResponse
from app.services.btcpay_client import BTCPayClient

router = APIRouter(prefix="/payments", tags=["payments"])


def payment_to_response(payment: Payment) -> InvoiceResponse:
    splits = [
        PaymentSplitResponse(
            id=split.id,
            label=split.split_target.label if split.split_target else None,
            ln_address=split.split_target.ln_address if split.split_target else None,
            amount_sats=split.amount_sats,
            status=split.status,
            btcpay_payout_state=split.btcpay_payout_state,
            payout_id=split.btcpay_payout_id,
            failure_reason=split.failure_reason,
            retry_count=split.retry_count,
            last_checked_at=split.last_checked_at,
            executed_at=split.executed_at or datetime.min,
        )
        for split in payment.splits
    ]
    return InvoiceResponse(
        id=payment.id,
        bolt11=payment.bolt11,
        amount_sats=payment.amount_sats,
        fiat_amount=payment.fiat_amount,
        fiat_currency=payment.fiat_currency,
        memo=payment.memo,
        status=payment.status,
        paid_at=payment.paid_at,
        splits=splits,
        created_at=payment.created_at,
    )


def _payment_status_filter(status_filter: str):
    if status_filter == "failed":
        return Payment.splits.any(PaymentSplit.status == "failed")
    if status_filter in {"pending", "in_progress", "completed"}:
        return Payment.splits.any(PaymentSplit.status == status_filter)
    return Payment.status == status_filter


@router.get("", response_model=InvoiceListResponse)
async def list_payments(
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> InvoiceListResponse:
    filters = [Payment.tenant_id == tenant.id]
    if status_filter:
        filters.append(_payment_status_filter(status_filter))
    if search:
        filters.append(Payment.memo.ilike(f"%{search}%"))
    if date_from:
        filters.append(Payment.created_at >= date_from)
    if date_to:
        filters.append(Payment.created_at <= date_to)

    query = (
        select(Payment)
        .where(*filters)
        .options(
            selectinload(Payment.splits).selectinload(PaymentSplit.split_target)
        )
        .order_by(Payment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    payments = list(result.scalars().unique().all())
    count_result = await session.execute(
        select(func.count()).select_from(Payment).where(*filters)
    )
    return InvoiceListResponse(
        items=[payment_to_response(payment) for payment in payments],
        total=count_result.scalar_one(),
    )


@router.get("/{payment_id}", response_model=InvoiceResponse)
async def get_payment(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> InvoiceResponse:
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
    return payment_to_response(payment)


@router.post(
    "/{payment_id}/splits/{split_id}/retry",
    response_model=PaymentSplitResponse,
)
async def retry_payment_split(
    payment_id: uuid.UUID,
    split_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> PaymentSplitResponse:
    result = await session.execute(
        select(PaymentSplit)
        .join(Payment, Payment.id == PaymentSplit.payment_id)
        .where(
            Payment.id == payment_id,
            Payment.tenant_id == tenant.id,
            PaymentSplit.id == split_id,
        )
        .options(selectinload(PaymentSplit.split_target))
    )
    split = result.scalar_one_or_none()
    if not split:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split not found")
    if split.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed payouts can be retried",
        )
    # Dynamic LND receivers (bolt11, no ln_address) are not auto-retryable yet:
    # a fresh invoice must be minted per attempt. Only ln_address targets requeue.
    if (
        tenant.adapter_type != "btcpay"
        or split.split_target is None
        or not split.split_target.ln_address
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This payout does not have a retryable BTCPay destination",
        )

    client = BTCPayClient(
        base_url=tenant.btcpay_url or "",
        api_key=tenant.btcpay_api_key or "",
        store_id=tenant.btcpay_store_id or "",
    )
    try:
        payout = await client.payout_to_ln_address(
            amount_sats=split.amount_sats,
            ln_address=split.split_target.ln_address,
            label=f"Retry → {split.split_target.label}",
        )
        payout_id = payout.get("id")
        if not payout_id:
            raise ValueError("BTCPay did not return a payout id")
        split.btcpay_payout_id = payout_id
        split.status = "in_progress"
        split.failure_reason = None
        split.retry_count += 1
        split.last_checked_at = None
        # The old payout's raw state ("Cancelled") no longer describes the new
        # payout; cleared until the next reconciliation check reads it.
        split.btcpay_payout_state = None
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"BTCPay payout retry failed: {exc}",
        )
    finally:
        await client.close()

    return PaymentSplitResponse(
        id=split.id,
        label=split.split_target.label,
        ln_address=split.split_target.ln_address,
        amount_sats=split.amount_sats,
        status=split.status,
        btcpay_payout_state=split.btcpay_payout_state,
        payout_id=split.btcpay_payout_id,
        failure_reason=split.failure_reason,
        retry_count=split.retry_count,
        last_checked_at=split.last_checked_at,
        executed_at=split.executed_at,
    )
