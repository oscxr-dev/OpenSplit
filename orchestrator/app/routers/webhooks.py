from __future__ import annotations

import hashlib
import hmac
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import SplitRule, Payment, Tenant
from app.schemas import LNBitsWebhookPayload
from app.services.lnbits_client import LNBitsClient
from app.services.btcpay_client import BTCPayClient
from app.services.split_engine import SplitEngine

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SATOSHIS_PER_BTC = Decimal("100000000")


def _verify_webhook_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _decimal_or_none(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _btc_to_sats(value: Decimal) -> int:
    return int((value * SATOSHIS_PER_BTC).to_integral_value())


def btcpay_invoice_amount_sats(invoice: dict, payment_methods: list[dict] | None = None) -> int:
    """Resolve the actual settled BTC amount for BTCPay POS/direct invoices.

    Fiat-denominated invoices expose their fiat total in invoice.amount, so the
    BTC/LN settled amount must come from payment-method data instead.
    """
    for method in payment_methods or []:
        method_id = str(method.get("paymentMethod") or method.get("paymentMethodId") or "")
        currency = str(method.get("currency") or "").upper()
        if "BTC" not in method_id.upper() and currency != "BTC":
            continue
        for field in ("paymentMethodPaid", "totalPaid", "amount"):
            amount = _decimal_or_none(method.get(field))
            if amount is not None and amount > 0:
                return _btc_to_sats(amount)

    raw = invoice.get("amount") or (invoice.get("checkout") or {}).get("amount")
    currency = str(invoice.get("currency") or "SATS").upper()
    amount = _decimal_or_none(raw)
    if amount is None:
        return 0
    if currency == "BTC":
        return _btc_to_sats(amount)
    if currency in {"SAT", "SATS"}:
        return int(amount.to_integral_value())
    return 0


@router.post("/lnbits/paid", status_code=status.HTTP_200_OK)
async def lnbits_paid_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Verify signature (soft: only reject if signature header present but invalid)
    body = await request.body()
    signature = request.headers.get("X-LNBits-Signature", "")
    if signature:
        # If LNBits sent a signature, it MUST match
        if not _verify_webhook_signature(body, signature, settings.lnbits_webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = LNBitsWebhookPayload.model_validate_json(body)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    # Find the pending payment by invoice_id (payment_hash)
    if not payload.checking_id and not payload.payment_hash:
        return {"status": "ignored", "reason": "no identifier"}

    lookup_id = payload.checking_id or payload.payment_hash
    result = await session.execute(
        select(Payment).where(Payment.invoice_id == lookup_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        # Try lookup by bolt11 (payment_request)
        if payload.payment_request:
            result = await session.execute(
                select(Payment).where(Payment.bolt11 == payload.payment_request)
            )
            payment = result.scalar_one_or_none()
    if not payment:
        return {"status": "ignored", "reason": f"payment {lookup_id} not found"}

    if payment.status != "pending":
        return {"status": "ok", "message": "already processed"}

    # Record split audit trail for the payment
    result = await session.execute(select(Tenant).where(Tenant.id == payment.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        client = LNBitsClient(tenant.lnbits_admin_key, tenant.lnbits_url)
        engine = SplitEngine(session, client)
        await engine.record_split(payment.id)
        await client.close()

    return {"status": "ok", "payment_id": str(payment.id)}

@router.post("/btcpay/{tenant_id}", status_code=status.HTTP_200_OK)
async def btcpay_webhook(
    tenant_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receives BTCPay Greenfield webhooks. On InvoiceSettled, calculates
    splits and executes payouts to each target's Lightning address.

    Idempotent and signature-verified (BTCPay-Sig header, HMAC-SHA256).
    """
    body = await request.body()

    # Resolve tenant
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant or tenant.adapter_type != "btcpay":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BTCPay tenant not found")

    # Verify signature if a secret is configured
    sig = request.headers.get("BTCPay-Sig", "")
    if tenant.btcpay_webhook_secret:
        if not BTCPayClient.verify_webhook_sig(tenant.btcpay_webhook_secret, body, sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # Parse event
    try:
        import json
        event = json.loads(body)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    event_type = event.get("type", "")
    # Only act on settled invoices (paid + confirmed)
    if event_type not in ("InvoiceSettled", "InvoicePaymentSettled"):
        return {"status": "ignored", "reason": f"event {event_type} not actionable"}

    invoice_id = event.get("invoiceId")
    if not invoice_id:
        return {"status": "ignored", "reason": "no invoiceId"}

    # Find the pending payment by invoice_id
    result = await session.execute(
        select(Payment).where(Payment.invoice_id == invoice_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        # Invoice created directly in BTCPay (POS/Request). Create the Payment now.
        meta = event.get("metadata") or {}
        amount_sats = 0
        fiat_amount = None
        fiat_currency = None
        _bc = None
        try:
            _bc = BTCPayClient(base_url=tenant.btcpay_url, api_key=tenant.btcpay_api_key, store_id=tenant.btcpay_store_id)
            inv = await _bc.get_invoice(invoice_id)
            payment_methods = await _bc.get_invoice_payment_methods(invoice_id)
            amount_sats = btcpay_invoice_amount_sats(inv, payment_methods)
            raw = inv.get("amount") or (inv.get("checkout") or {}).get("amount")
            cur = (inv.get("currency") or "").upper()
            if cur and cur not in {"BTC", "SAT", "SATS"}:
                fiat_amount = _decimal_or_none(raw)
                fiat_currency = cur
        except Exception as e:
            print("WARN amount fetch:", e)
        finally:
            if _bc is not None:
                await _bc.close()
        if amount_sats <= 0:
            return {"status": "ignored", "reason": "could not resolve settled BTC amount"}
        # default split rule for this tenant
        rule_res = await session.execute(
            select(SplitRule).where(SplitRule.tenant_id == tenant.id, SplitRule.active == True)
        )
        rule = rule_res.scalars().first()
        if not rule:
            return {"status": "ignored", "reason": "no active split rule"}
        payment = Payment(
            invoice_id=invoice_id,
            bolt11=meta.get("bolt11", ""),
            amount_sats=amount_sats,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            memo=meta.get("itemDesc", "BTCPay POS"),
            status="pending",
            tenant_id=tenant.id,
            split_rule_id=rule.id,
        )
        session.add(payment)
        try:
            await session.flush()
        except IntegrityError:
            # Another webhook already created this invoice's payment; treat as
            # already processed instead of erroring.
            await session.rollback()
            existing = await session.execute(
                select(Payment).where(Payment.invoice_id == invoice_id)
            )
            payment = existing.scalar_one_or_none()
            return {
                "status": "ok",
                "message": "already processed",
                "payment_id": str(payment.id) if payment else None,
            }

    if payment.status != "pending":
        return {"status": "ok", "message": "already processed"}

    # Execute splits via BTCPay payouts
    btcpay = BTCPayClient(
        base_url=tenant.btcpay_url,
        api_key=tenant.btcpay_api_key,
        store_id=tenant.btcpay_store_id,
    )
    engine = SplitEngine(session, lnbits_client=None)  # lnbits not used in btcpay path
    await engine.execute_splits_btcpay(payment.id, btcpay)
    await btcpay.close()

    return {"status": "ok", "payment_id": str(payment.id)}
