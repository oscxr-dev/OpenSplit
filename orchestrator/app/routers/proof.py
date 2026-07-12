"""Split proof endpoints.

GET returns a clear, auditable proof of how a single payment was split across
its members/targets, including a sanity integrity check that the split amounts
sum to the payment amount. It is strictly read-only.

POST /{id}/proof/sign signs that proof with the team's Nostr key (see
services/nostr_proof.py for the bundle contract and key custody). Its ONLY
write is the informational payments.nostr_proof_event column — it never
touches money state, the split engine, payouts, webhooks, or reconciliation.

Tenant-scoped — a payment is only visible to the tenant that owns it.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.deps import get_current_tenant, get_current_user
from app.core.nostr_keys import (
    npub_from_hex,
    pubkey_hex_from_seckey,
    seckey_bytes_from_env_value,
)
from app.database import get_session
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget, Tenant, User
from app.schemas import (
    NostrProofResponse,
    ProofIntegrity,
    ProofSplitResponse,
    SplitProofResponse,
)
from app.services.nostr_proof import (
    canonical_proof_bundle,
    sign_proof_event,
    verify_proof_event,
)

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
    # Lightning settlement proof (verbatim from BTCPay; see PaymentSplit model).
    ln_preimage: str | None = None
    ln_payment_hash: str | None = None


def nostr_proof_from_stored(event_json: str | None) -> NostrProofResponse | None:
    """Parse a stored signed event into its display schema. Pure.

    The stored value is our own verbatim write, so a parse failure means DB
    tampering or corruption — surface that as "no proof" rather than a 500.
    """
    if not event_json:
        return None
    try:
        event = json.loads(event_json)
        return NostrProofResponse(
            event_json=event_json,
            event_id=event["id"],
            pubkey=event["pubkey"],
            npub=npub_from_hex(event["pubkey"]),
            kind=event["kind"],
            created_at=event["created_at"],
        )
    except Exception:
        return None


def build_proof(
    *,
    payment_id: uuid.UUID,
    amount_sats: int,
    unallocated_store_sats: int = 0,
    pending_remainder_sats: int = 0,
    status: str,
    split_rule_id: uuid.UUID | None,
    split_rule_version: int | None,
    rule_fingerprint: str | None = None,
    nostr_proof: NostrProofResponse | None = None,
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
            ln_preimage=row.ln_preimage,
            ln_payment_hash=row.ln_payment_hash,
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
        rule_fingerprint=rule_fingerprint,
        nostr_proof=nostr_proof,
        members=members,
        integrity=integrity,
    )


async def _load_payment(
    payment_id: uuid.UUID, tenant: Tenant, session: AsyncSession
) -> Payment:
    result = await session.execute(
        select(Payment)
        .where(Payment.id == payment_id, Payment.tenant_id == tenant.id)
        .options(selectinload(Payment.splits).selectinload(PaymentSplit.split_target))
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


def _proof_rows(payment: Payment) -> list[ProofSplitRow]:
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
                ln_preimage=split.ln_preimage,
                ln_payment_hash=split.ln_payment_hash,
            )
        )
    return rows


@router.get("/{payment_id}/proof", response_model=SplitProofResponse)
async def get_split_proof(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> SplitProofResponse:
    payment = await _load_payment(payment_id, tenant, session)

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

    return build_proof(
        payment_id=payment.id,
        amount_sats=payment.amount_sats,
        unallocated_store_sats=payment.unallocated_store_sats,
        pending_remainder_sats=payment.pending_remainder_sats,
        status=payment.status,
        split_rule_id=payment.split_rule_id,
        split_rule_version=split_rule_version,
        rule_fingerprint=payment.rule_fingerprint,
        nostr_proof=nostr_proof_from_stored(payment.nostr_proof_event),
        rows=_proof_rows(payment),
    )


@router.post("/{payment_id}/proof/sign", response_model=NostrProofResponse)
async def sign_split_proof(
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> NostrProofResponse:
    """Sign this payment's proof bundle with the team's Nostr key.

    Preconditions (in check order):
      * ORCHESTRATOR_NOSTR_SECKEY set and valid        → else 422
      * tenant has a configured nostr_pubkey            → else 422
      * env key derives exactly that pubkey             → else 409 (guards a
        multi-tenant instance from signing tenant B's proofs with tenant A's
        key, and guarantees the event verifies against the configured key)
      * payment status is "paid" (splits terminal, so the bundle is stable)
                                                        → else 409

    Idempotent: if the stored event already covers the identical bundle under
    the same key it is returned as-is; otherwise (state backfilled, key
    rotated) a fresh event replaces it — one column, so duplicates are
    impossible by construction. Missing preimages/fingerprint do NOT block
    signing: they are included as honest nulls (see services/nostr_proof.py).
    """
    if not settings.nostr_seckey.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nostr signing is not configured on this server "
            "(set ORCHESTRATOR_NOSTR_SECKEY)",
        )
    try:
        seckey = seckey_bytes_from_env_value(settings.nostr_seckey)
    except ValueError as exc:
        # Message comes from our own validator and never echoes key material.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if not tenant.nostr_pubkey:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Configure the team's Nostr public key in Settings first",
        )
    derived_pubkey = pubkey_hex_from_seckey(seckey)
    if derived_pubkey != tenant.nostr_pubkey:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The server's signing key does not match this team's configured "
            "Nostr public key — refusing to sign",
        )

    payment = await _load_payment(payment_id, tenant, session)
    if payment.status != "paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only fully paid payments can be signed — the split set must "
            "be final before it is sealed",
        )

    settled_at = payment.paid_at or payment.created_at
    bundle = canonical_proof_bundle(
        payment_id=payment.id,
        amount_sats=payment.amount_sats,
        rule_fingerprint=payment.rule_fingerprint,
        splits=_proof_rows(payment),
        timestamp=int(settled_at.timestamp()),
    )

    # Idempotency: identical bundle already signed by this key → return it.
    if payment.nostr_proof_event:
        try:
            stored = json.loads(payment.nostr_proof_event)
        except Exception:
            stored = None
        if (
            stored
            and stored.get("content") == bundle
            and stored.get("pubkey") == derived_pubkey
        ):
            return nostr_proof_from_stored(payment.nostr_proof_event)

    event = sign_proof_event(seckey, bundle, int(settled_at.timestamp()))
    # Verify-on-generate: never persist an event we could not verify ourselves.
    if not verify_proof_event(event):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signed event failed local verification — nothing was stored",
        )

    payment.nostr_proof_event = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    await session.commit()
    return nostr_proof_from_stored(payment.nostr_proof_event)
