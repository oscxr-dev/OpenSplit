from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Payment, PaymentSplit, Tenant, User
from app.schemas import (
    DashboardSummaryResponse,
    LiquiditySummary,
    RecentPaymentResponse,
    TodaySummary,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummaryResponse:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_result = await session.execute(
        select(
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount_sats), 0),
            func.sum(Payment.fiat_amount),
            func.max(Payment.fiat_currency),
        ).where(
            Payment.tenant_id == tenant.id,
            Payment.status == "paid",
            Payment.paid_at >= today_start,
        )
    )
    count, total_sats, total_fiat, fiat_currency = today_result.one()

    failed_result = await session.execute(
        select(func.count(PaymentSplit.id))
        .join(Payment, Payment.id == PaymentSplit.payment_id)
        .where(Payment.tenant_id == tenant.id, PaymentSplit.status == "failed")
    )

    recent_result = await session.execute(
        select(Payment)
        .where(Payment.tenant_id == tenant.id)
        .options(selectinload(Payment.splits))
        .order_by(Payment.created_at.desc())
        .limit(5)
    )
    recent = []
    for payment in recent_result.scalars().unique().all():
        completed = sum(split.status == "completed" for split in payment.splits)
        total = len(payment.splits)
        recent.append(
            RecentPaymentResponse(
                id=payment.id,
                amount_sats=payment.amount_sats,
                fiat_amount=payment.fiat_amount,
                fiat_currency=payment.fiat_currency,
                status=payment.status,
                paid_at=payment.paid_at,
                splits_summary=f"{completed}/{total} completados" if total else "Sin reparto",
            )
        )

    return DashboardSummaryResponse(
        # Channel liquidity is an F2 adapter. Returning unavailable is explicit
        # and avoids inventing a balance from payment history.
        liquidity=LiquiditySummary(status="unavailable"),
        today=TodaySummary(
            count=count,
            total_sats=total_sats,
            total_fiat=Decimal(total_fiat) if total_fiat is not None else None,
            fiat_currency=fiat_currency,
        ),
        failed_count=failed_result.scalar_one(),
        recent_payments=recent,
    )
