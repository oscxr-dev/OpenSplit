from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.percentages import quantized_total
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget
from app.services.lnbits_client import LNBitsClient
from app.services.btcpay_client import BTCPayClient
from app.services.lnd_client import LNDClient, load_lnd_receiver


def calculate_splits(
    amount_sats: int, targets: list[SplitTarget]
) -> list[tuple[SplitTarget, int]]:
    """Exact integer distribution via largest remainder algorithm.
    
    Guarantee: sum(splits) == amount_sats for any valid amount and percentages.
    Tiebreaker: when fractional parts are equal, lower order wins.
    """
    if amount_sats <= 0:
        raise ValueError("amount_sats must be positive")

    # Same 2-decimal total the API enforces, so any rule the API accepts is
    # processable here.
    total_pct = quantized_total(t.percentage for t in targets)
    if total_pct != Decimal("100"):
        raise ValueError(f"Percentages must sum to 100, got {total_pct}")

    # Step 1: exact fractional amount per target
    exact_amounts: list[tuple[SplitTarget, Decimal]] = [
        (t, Decimal(amount_sats) * Decimal(str(t.percentage)) / Decimal("100"))
        for t in targets
    ]

    # Step 2: floor each
    floor_amounts: list[tuple[SplitTarget, int, Decimal]] = [
        (t, int(exact.to_integral_value(rounding=ROUND_DOWN)), exact)
        for t, exact in exact_amounts
    ]

    # Step 3: remainder in whole sats
    distributed = sum(amt for _, amt, _ in floor_amounts)
    remainder = amount_sats - distributed

    # Step 4: sort by lost fraction descending, assign 1 sat to top N
    fractions = sorted(
        floor_amounts,
        key=lambda x: (x[2] - x[1], -x[0].order),  # largest fraction, then lower order
        reverse=True,
    )

    result: dict[str, tuple[SplitTarget, int]] = {}
    for i, (target, floor_amt, _) in enumerate(fractions):
        extra = 1 if i < remainder else 0
        result[str(target.id)] = (target, floor_amt + extra)

    # Return in original target order
    return [result[str(t.id)] for t in targets]


def derive_payment_status(splits: list[PaymentSplit]) -> str:
    """Parent status from its splits. "paid" means everything payable was paid;
    a 0-sat "skipped" split counts as resolved, not a failure."""
    statuses = [s.status for s in splits]
    if not statuses:
        return "paid"
    settled_ok = {"completed", "skipped"}
    not_delivered = {"failed", "cancelled"}
    if all(s in settled_ok for s in statuses):
        return "paid"
    if all(s in not_delivered for s in statuses):
        return "failed"
    if any(s in not_delivered for s in statuses):
        return "partial"
    return "in_progress"


class SplitEngine:
    """Records the split audit trail for a payment."""

    def __init__(self, session: AsyncSession, lnbits_client: LNBitsClient | None = None) -> None:
        self.session = session
        self.lnbits = lnbits_client

    async def record_split(self, payment_id: uuid.UUID) -> list[PaymentSplit]:
        # Lock the row so concurrent processors serialize on the status check.
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != "pending":
            await self.session.commit()  # release the row lock before returning
            return payment.splits

        # Find active rule
        result = await self.session.execute(
            select(SplitRule).where(
                SplitRule.tenant_id == payment.tenant_id, SplitRule.active == True
            )
        )
        rule = result.scalar_one_or_none()

        if rule is None:
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            await self.session.commit()
            return []

        # Load targets
        result = await self.session.execute(
            select(SplitTarget)
            .where(SplitTarget.split_rule_id == rule.id)
            .where(SplitTarget.percentage > 0)
            .order_by(SplitTarget.order)
        )
        targets: list[SplitTarget] = list(result.scalars().all())

        # Calculate exact split amounts (largest remainder algorithm)
        splits = calculate_splits(payment.amount_sats, targets)

        # Record audit trail for the calculated split
        records: list[PaymentSplit] = []
        for target, amount in splits:
            records.append(
                PaymentSplit(
                    payment_id=payment.id,
                    split_target_id=target.id,
                    amount_sats=amount,
                    status="completed" if amount > 0 else "skipped",
                )
            )
            self.session.add(records[-1])

        payment.status = derive_payment_status(records)
        payment.split_rule_id = rule.id
        payment.paid_at = datetime.now(timezone.utc)
        await self.session.commit()
        return records

    async def execute_splits_btcpay(
        self, payment_id: uuid.UUID, btcpay: BTCPayClient
    ) -> list[PaymentSplit]:
        """For BTCPay tenants: calculate splits AND actively send payouts
        to each target's Lightning address. Records audit trail with the
        payout id and initial status per target. Confirmation is handled by
        the payout reconciliation worker.

        Idempotent: if payment already has splits, returns them unchanged.
        """
        # Lock the row so concurrent processors serialize on the status check.
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")

        # Status leaves "pending" before payouts are sent, so a waiting processor
        # that finds it already claimed must stop here. Commit to release the lock.
        if payment.status != "pending":
            await self.session.commit()
            return payment.splits

        # Find active rule
        result = await self.session.execute(
            select(SplitRule).where(
                SplitRule.tenant_id == payment.tenant_id, SplitRule.active == True
            )
        )
        rule = result.scalar_one_or_none()

        if rule is None:
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            await self.session.commit()
            return []

        # Load targets in order
        result = await self.session.execute(
            select(SplitTarget)
            .where(SplitTarget.split_rule_id == rule.id)
            .where(SplitTarget.percentage > 0)
            .order_by(SplitTarget.order)
        )
        targets: list[SplitTarget] = list(result.scalars().all())

        # Exact split amounts (largest remainder algorithm — same as LNbits path)
        splits = calculate_splits(payment.amount_sats, targets)

        # Claim as in_progress and commit (releasing the lock) before sending any
        # payout, so a concurrent processor sees a non-pending status and never
        # pays the same invoice. Final status is set after the payout loop.
        payment.status = "in_progress"
        payment.split_rule_id = rule.id
        payment.paid_at = datetime.now(timezone.utc)
        await self.session.commit()

        # A successful API response only means BTCPay accepted the order, not
        # that Lightning delivery completed.
        records: list[PaymentSplit] = []
        for target, amount in splits:
            if amount <= 0:
                # Share rounded to 0 sats: nothing payable, so skip the payout.
                record = PaymentSplit(
                    payment_id=payment.id,
                    split_target_id=target.id,
                    amount_sats=0,
                    status="skipped",
                )
                self.session.add(record)
                records.append(record)
                continue
            payout_id: str | None = None
            payout_status = "pending"
            failure_reason: str | None = None
            # Dynamic LND receivers (e.g. Carol, Dave for the demo): mint a
            # fresh BOLT11 invoice for the exact split amount on the recipient's
            # own LND node, then hand that invoice to BTCPay as the destination.
            # Credentials come from local env only (see lnd_client.load_*).
            receiver = load_lnd_receiver(target.label)
            if receiver is not None:
                lnd = LNDClient(receiver)
                try:
                    bolt11 = await lnd.create_invoice(
                        amount_sats=amount,
                        memo=f"{rule.name} → {target.label}",
                    )
                    payout = await btcpay.payout_to_bolt11(
                        bolt11=bolt11,
                        label=f"{rule.name} → {target.label}",
                    )
                    payout_id = payout.get("id")
                    if payout_id:
                        payout_status = "in_progress"
                    else:
                        payout_status = "failed"
                        failure_reason = "BTCPay aceptó la solicitud sin devolver un payout id."
                except Exception as exc:
                    payout_status = "failed"
                    failure_reason = str(exc)[:1000]
                finally:
                    await lnd.close()
            elif not target.ln_address:
                payout_status = "failed"
                failure_reason = "El destino no tiene una Lightning address configurada."
            else:
                try:
                    payout = await btcpay.payout_to_ln_address(
                        amount_sats=amount,
                        ln_address=target.ln_address,
                        label=f"{rule.name} → {target.label}",
                    )
                    payout_id = payout.get("id")
                    if payout_id:
                        payout_status = "in_progress"
                    else:
                        payout_status = "failed"
                        failure_reason = "BTCPay aceptó la solicitud sin devolver un payout id."
                except Exception as exc:
                    payout_status = "failed"
                    failure_reason = str(exc)[:1000]

            record = PaymentSplit(
                payment_id=payment.id,
                split_target_id=target.id,
                amount_sats=amount,
                btcpay_payout_id=payout_id,
                status=payout_status,
                failure_reason=failure_reason,
            )
            self.session.add(record)
            records.append(record)

        payment.status = derive_payment_status(records)
        await self.session.commit()
        return records
