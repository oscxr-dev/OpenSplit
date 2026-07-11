from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget, Tenant, User
from app.schemas import InvoiceCreateRequest, InvoiceListResponse, InvoiceResponse, PaymentSplitResponse
from app.services.lnbits_client import LNBitsClient

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _payment_to_response(payment: Payment) -> InvoiceResponse:
    splits = []
    if payment.splits:
        splits = [
            PaymentSplitResponse(
                id=s.id,
                label=s.split_target.label if s.split_target else None,
                amount_sats=s.amount_sats,
                status=s.status,
                btcpay_payout_state=s.btcpay_payout_state,
                ln_preimage=s.ln_preimage,
                ln_payment_hash=s.ln_payment_hash,
                executed_at=s.executed_at or datetime.min,
            )
            for s in payment.splits
        ]
    return InvoiceResponse(
        id=payment.id,
        bolt11=payment.bolt11,
        amount_sats=payment.amount_sats,
        memo=payment.memo,
        status=payment.status,
        paid_at=payment.paid_at,
        splits=splits,
        created_at=payment.created_at,
    )


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: InvoiceCreateRequest,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> InvoiceResponse:
    # Multiple rules can be active (each is a board tab). For invoice creation we
    # pick a single deterministic default: the newest active rule (highest
    # version, then most recently created). With one active rule this is simply
    # that rule, preserving the original single-active behaviour.
    result = await session.execute(
        select(SplitRule)
        .where(SplitRule.tenant_id == tenant.id, SplitRule.active == True)
        .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
    )
    active_rule = result.scalars().first()

    # Call LNBits to create the actual invoice
    client = LNBitsClient(tenant.lnbits_admin_key, tenant.lnbits_url)
    try:
        lnbits_invoice = await client.create_invoice(
            body.amount_sats, body.memo or "OpenSplit",
            webhook_url=f"http://orchestrator:8000/api/v1/webhooks/lnbits/paid",
        )
        bolt11 = lnbits_invoice.get("payment_request")
        payment_hash = lnbits_invoice.get("payment_hash")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LNBits error: {e}")
    finally:
        await client.close()

    # Create local payment record
    payment = Payment(
        tenant_id=tenant.id,
        invoice_id=payment_hash,
        bolt11=bolt11,
        amount_sats=body.amount_sats,
        memo=body.memo,
        status="pending",
        split_rule_id=active_rule.id if active_rule else None,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return _payment_to_response(payment)


@router.get("/{payment_id}", response_model=InvoiceResponse)
async def get_invoice(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> InvoiceResponse:
    result = await session.execute(
        select(Payment).where(Payment.id == payment_id, Payment.tenant_id == tenant.id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    # Auto-reconcile pending invoices: check LNBits for payment status
    if payment.status == "pending" and payment.invoice_id:
        client = LNBitsClient(tenant.lnbits_admin_key, tenant.lnbits_url)
        try:
            lnbits_payment = await client.check_invoice(payment.invoice_id)
            if lnbits_payment:  # check_invoice already validated paid=True
                from app.services.split_engine import SplitEngine
                engine = SplitEngine(session, client)
                await engine.record_split(payment.id)
                await session.refresh(payment)
        except Exception:
            pass  # Reconciliation is best-effort; don't block the GET
        finally:
            await client.close()

    return _payment_to_response(payment)


@router.post("/reconcile", status_code=status.HTTP_200_OK)
async def reconcile_invoices(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reconcile all pending invoices by checking LNBits payment status."""
    result = await session.execute(
        select(Payment).where(
            Payment.tenant_id == tenant.id,
            Payment.status == "pending",
        )
    )
    pending = result.scalars().all()

    if not pending:
        return {"reconciled": 0, "message": "No pending invoices"}

    client = LNBitsClient(tenant.lnbits_admin_key, tenant.lnbits_url)
    reconciled = 0
    try:
        from app.services.split_engine import SplitEngine
        engine = SplitEngine(session, client)
        for payment in pending:
            if not payment.invoice_id:
                continue
            lnbits_payment = await client.check_invoice(payment.invoice_id)
            if lnbits_payment:  # check_invoice already validated paid=True
                await engine.record_split(payment.id)
                reconciled += 1
        await session.commit()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Reconciliation error: {e}",
        )
    finally:
        await client.close()

    return {"reconciled": reconciled, "pending_remaining": len(pending) - reconciled}


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    status_filter: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> InvoiceListResponse:
    q = select(Payment).where(Payment.tenant_id == tenant.id)
    if status_filter:
        q = q.where(Payment.status == status_filter)
    q = q.order_by(Payment.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(q)
    payments = result.scalars().all()

    count_result = await session.execute(
        select(func.count()).select_from(Payment).where(Payment.tenant_id == tenant.id)
    )
    total = count_result.scalar() or 0

    return InvoiceListResponse(
        items=[_payment_to_response(p) for p in payments],
        total=total,
    )
