from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.percentages import quantized_total
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget
from app.services.lnbits_client import LNBitsClient
from app.services.btcpay_client import BTCPayClient
from app.services.lnd_client import LNDClient, load_lnd_receiver
from app.services.proof_hash import rule_fingerprint


@dataclass(frozen=True)
class SplitAllocation:
    """Auditable result of integer-only split math.

    ``splits`` contains only whole-sat target payouts.
    ``unallocated_store_sats`` is the intentional store remainder from partial
    rules where total target percentages are < 100%.
    ``pending_remainder_sats`` is the whole-sat dust that cannot be assigned to
    either targets or the intentional store remainder without inventing
    fractional sats, plus tiny-payment amounts that are too small to give all
    rule targets a fair minimum 1-sat payout. It belongs to store treasury until
    a future explicit withdrawal or redistribution policy exists.
    """

    splits: list[tuple[SplitTarget, int]]
    allocated_sats: int
    unallocated_store_sats: int
    pending_remainder_sats: int


def calculate_split_allocation(
    amount_sats: int, targets: list[SplitTarget]
) -> SplitAllocation:
    """Integer split distribution using largest remainder + pending remainder.

    Policy:
    - calculate exact shares from payment amount and percentages;
    - floor each target share to whole sats;
    - distribute payable leftover sats to largest fractional remainders;
    - break ties deterministically by rule target order, then target id;
    - preserve partial rules: the intentionally unallocated store share is not
      paid to targets;
    - if the target-payable amount is smaller than the number of active targets,
      do not pay only one winner; keep that target-payable amount as pending
      store treasury instead;
    - if a whole sat is left after flooring both the payable target share and
      the intentional store share, keep it as ``pending_remainder_sats``.
    """
    if amount_sats <= 0:
        raise ValueError("amount_sats must be positive")

    # Same 2-decimal total the API enforces, so any rule the API accepts is
    # processable here. Partial rules (< 100%) are allowed; over-allocation is not.
    total_pct = quantized_total(t.percentage for t in targets)
    if total_pct <= Decimal("0") or total_pct > Decimal("100"):
        raise ValueError(f"Percentages must total >0 and <=100, got {total_pct}")

    # Step 1: exact fractional amount per target.
    exact_amounts: list[tuple[SplitTarget, Decimal]] = [
        (t, Decimal(amount_sats) * Decimal(str(t.percentage)) / Decimal("100"))
        for t in targets
    ]

    # Step 2: floor each target payout to whole sats.
    floor_amounts: list[tuple[SplitTarget, int, Decimal]] = [
        (t, int(exact.to_integral_value(rounding=ROUND_DOWN)), exact)
        for t, exact in exact_amounts
    ]

    # Step 3: only the configured target share is payable to targets. The
    # intentional store share is accounted separately, and any indivisible sat
    # left between those two floors becomes pending remainder.
    payable_target_sats = int(
        (Decimal(amount_sats) * total_pct / Decimal("100")).to_integral_value(rounding=ROUND_DOWN)
    )
    unallocated_pct = Decimal("100") - total_pct
    unallocated_store_sats = int(
        (Decimal(amount_sats) * unallocated_pct / Decimal("100")).to_integral_value(rounding=ROUND_DOWN)
    )
    pending_remainder_sats = amount_sats - payable_target_sats - unallocated_store_sats
    if pending_remainder_sats < 0:
        # Defensive guard: Decimal flooring should prevent this, but never let
        # rounding metadata make the audit trail negative.
        pending_remainder_sats = 0

    active_target_count = len(targets)
    if payable_target_sats < active_target_count:
        pending_remainder_sats += payable_target_sats
        payable_target_sats = 0

    distributed_floor_sats = sum(amt for _, amt, _ in floor_amounts)
    if payable_target_sats == 0:
        floor_amounts = [(target, 0, exact) for target, _, exact in floor_amounts]
        distributed_floor_sats = 0
    remainder_to_targets = payable_target_sats - distributed_floor_sats

    # Step 4: sort by lost fraction descending, then stable rule order and id.
    fractions = sorted(
        floor_amounts,
        key=lambda x: (-(x[2] - x[1]), x[0].order, str(x[0].id)),
    )

    result: dict[str, tuple[SplitTarget, int]] = {}
    for i, (target, floor_amt, _) in enumerate(fractions):
        extra = 1 if i < remainder_to_targets else 0
        result[str(target.id)] = (target, floor_amt + extra)

    splits = [result[str(t.id)] for t in targets]
    return SplitAllocation(
        splits=splits,
        allocated_sats=sum(amount for _, amount in splits),
        unallocated_store_sats=unallocated_store_sats,
        pending_remainder_sats=pending_remainder_sats,
    )


def calculate_splits(
    amount_sats: int, targets: list[SplitTarget]
) -> list[tuple[SplitTarget, int]]:
    """Backward-compatible split list for callers that only need target payouts.

    See ``calculate_split_allocation`` for the full auditable allocation,
    including intentional store remainder and pending indivisible remainder.
    """
    return calculate_split_allocation(amount_sats, targets).splits


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
            select(SplitRule)
            .where(
                SplitRule.tenant_id == payment.tenant_id, SplitRule.active == True
            )
            .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
        )
        rule = result.scalars().first()

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

        # Calculate exact split amounts plus auditable remainder metadata.
        allocation = calculate_split_allocation(payment.amount_sats, targets)
        splits = allocation.splits
        payment.unallocated_store_sats = allocation.unallocated_store_sats
        payment.pending_remainder_sats = allocation.pending_remainder_sats

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
        # Fingerprint over ALL of the rule's stored targets (rule.targets), not
        # the >0% subset used for allocation — it identifies the rule version.
        payment.rule_fingerprint = rule_fingerprint(rule, rule.targets)
        payment.paid_at = datetime.now(timezone.utc)
        await self.session.commit()
        return records

    async def execute_splits_btcpay(
        self, payment_id: uuid.UUID, btcpay: BTCPayClient, *, resume: bool = False
    ) -> list[PaymentSplit]:
        """For BTCPay tenants: calculate splits AND actively send payouts
        to each target's Lightning address. Records audit trail with the
        payout id and initial status per target. Confirmation is handled by
        the payout reconciliation worker.

        Durability: each target's row is committed BEFORE its BTCPay call
        (pre-flight marker) and its payout id is committed immediately AFTER,
        so a crash mid-loop never orphans a created payout and a target with
        no row provably never had a payout attempted.

        Idempotent: if payment already has splits, returns them unchanged.
        ``resume=True`` re-enters a crashed "in_progress" payment and finishes
        only the targets without a recorded payout; it replays the rule
        captured at claim time, never the currently active one. Only call it
        when no other processor can still be mid-flight for this payment.
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
        # Only an explicit resume may re-enter a claimed-but-unfinished payment.
        resuming = (
            resume
            and payment.status == "in_progress"
            and payment.split_rule_id is not None
        )
        if payment.status != "pending" and not resuming:
            await self.session.commit()
            return payment.splits

        if resuming:
            # Replay the rule recorded when the payment was claimed, not
            # whatever rule is active now, so amounts match the original run.
            result = await self.session.execute(
                select(SplitRule).where(SplitRule.id == payment.split_rule_id)
            )
            rule = result.scalar_one()
        else:
            # Find active rule
            result = await self.session.execute(
                select(SplitRule)
                .where(
                    SplitRule.tenant_id == payment.tenant_id, SplitRule.active == True
                )
                .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
            )
            rule = result.scalars().first()

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

        # Exact split amounts plus auditable remainder metadata — same as LNbits path.
        allocation = calculate_split_allocation(payment.amount_sats, targets)
        splits = allocation.splits

        # Claim as in_progress and commit (releasing the lock) before sending any
        # payout, so a concurrent processor sees a non-pending status and never
        # pays the same invoice. Final status is set after the payout loop.
        if not resuming:
            payment.status = "in_progress"
            payment.split_rule_id = rule.id
            # Fingerprint over ALL of the rule's stored targets (rule.targets),
            # frozen in the same commit that claims the rule for this payment.
            payment.rule_fingerprint = rule_fingerprint(rule, rule.targets)
            payment.unallocated_store_sats = allocation.unallocated_store_sats
            payment.pending_remainder_sats = allocation.pending_remainder_sats
            payment.paid_at = datetime.now(timezone.utc)
        await self.session.commit()

        # Rows already recorded for this payment are the idempotency guard:
        # a target whose row carries a payout id — or any status past the
        # pre-flight "pending" — must never get a second payout.
        result = await self.session.execute(
            select(PaymentSplit).where(PaymentSplit.payment_id == payment.id)
        )
        prior_by_target = {s.split_target_id: s for s in result.scalars()}

        # A successful API response only means BTCPay accepted the order, not
        # that Lightning delivery completed.
        records: list[PaymentSplit] = []
        for target, amount in splits:
            prior = prior_by_target.get(target.id)
            if prior is not None and (
                prior.btcpay_payout_id is not None or prior.status != "pending"
            ):
                records.append(prior)
                continue
            if amount <= 0:
                # Share rounded to 0 sats: nothing payable, so skip the payout.
                record = PaymentSplit(
                    payment_id=payment.id,
                    split_target_id=target.id,
                    amount_sats=0,
                    status="skipped",
                )
                self.session.add(record)
                await self.session.commit()
                records.append(record)
                continue

            if prior is None:
                # Durable pre-flight marker committed BEFORE the BTCPay call:
                # after a crash, a target with no row provably never had a
                # payout attempted, so resume can create one safely.
                record = PaymentSplit(
                    payment_id=payment.id,
                    split_target_id=target.id,
                    amount_sats=amount,
                    status="pending",
                )
                self.session.add(record)
            else:
                # Interrupted pre-flight row from a crashed run: no payout id
                # was recorded, so retry it with the amount already audited.
                record = prior
                record.retry_count += 1
                amount = record.amount_sats
            await self.session.commit()

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

            # Persist this target's payout id/status before touching the next
            # target, so a crash mid-loop never loses a created payout.
            record.btcpay_payout_id = payout_id
            record.status = payout_status
            record.failure_reason = failure_reason
            await self.session.commit()
            records.append(record)

        # Derive the parent status from ALL of its split rows — a resumed
        # payment may have rows beyond the ones this run touched.
        result = await self.session.execute(
            select(PaymentSplit).where(PaymentSplit.payment_id == payment.id)
        )
        payment.status = derive_payment_status(list(result.scalars()))
        await self.session.commit()
        return records
