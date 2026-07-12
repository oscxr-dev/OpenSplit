"""POST /payments/{id}/proof/sign — the Nostr proof signing endpoint.

Runs against Postgres on the dedicated orchestrator_test database, calling the
router coroutines directly (same style as test_rule_fingerprint_capture.py).
Verification of anything signed here goes through the independent pure-Python
BIP-340/NIP-01 implementations in test_nostr_proof, never the signing code.

Custody invariants exercised throughout: the private key exists only as the
monkeypatched settings.nostr_seckey value, and no response or stored row may
ever contain it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.routers.proof import get_split_proof, sign_split_proof
from app.services.nostr_proof import OPENSPLIT_PROOF_KIND, canonical_proof_bundle

from test_nostr_proof import (  # independent verifier + fixed test identity
    PUBKEY_HEX,
    SECKEY,
    independent_event_id,
    schnorr_verify,
)

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

SECKEY_HEX = SECKEY.hex()
PAID_AT = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
PREIMAGE = "c6" * 32
PAYMENT_HASH = "77" * 32
FINGERPRINT = "bc0c49b1591b2d47dbaf19324e09fdf78517114e314b4346ed39cb5397b322aa"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def Session(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def signing_env(monkeypatch):
    monkeypatch.setattr(settings, "nostr_seckey", SECKEY_HEX)


async def _seed(
    Session,
    *,
    nostr_pubkey: str | None = PUBKEY_HEX,
    payment_status: str = "paid",
    with_proof_columns: bool = True,
) -> tuple[Tenant, uuid.UUID]:
    """Tenant + frozen rule + one payment with two splits (Carol completed
    with settlement proof, Dave completed without one)."""
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Nostr-{tenant_id.hex[:8]}",
            adapter_type="btcpay",
            nostr_pubkey=nostr_pubkey,
            active=True,
        )
        rule = SplitRule(tenant_id=tenant_id, name="Signed", active=True, version=1)
        s.add_all([tenant, rule])
        await s.flush()
        carol = SplitTarget(
            split_rule_id=rule.id, label="Carol", ln_address="carol@ln.test",
            percentage=60, order=0,
        )
        dave = SplitTarget(
            split_rule_id=rule.id, label="Dave", ln_address="dave@ln.test",
            percentage=40, order=1,
        )
        s.add_all([carol, dave])
        await s.flush()
        payment_id = uuid.uuid4()
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant_id,
                invoice_id=f"inv-{payment_id.hex[:8]}",
                amount_sats=21001,
                status=payment_status,
                split_rule_id=rule.id,
                rule_fingerprint=FINGERPRINT if with_proof_columns else None,
                paid_at=PAID_AT,
            )
        )
        s.add_all(
            [
                PaymentSplit(
                    payment_id=payment_id,
                    split_target_id=carol.id,
                    amount_sats=14001,
                    status="completed",
                    ln_preimage=PREIMAGE if with_proof_columns else None,
                    ln_payment_hash=PAYMENT_HASH if with_proof_columns else None,
                ),
                PaymentSplit(
                    payment_id=payment_id,
                    split_target_id=dave.id,
                    amount_sats=7000,
                    status="completed",
                ),
            ]
        )
        await s.commit()
    return tenant, payment_id


async def _sign(Session, tenant, payment_id):
    async with Session() as s:
        return await sign_split_proof(
            payment_id, current_user=None, tenant=tenant, session=s
        )


async def _stored_payment(Session, payment_id) -> Payment:
    async with Session() as s:
        return (
            await s.execute(select(Payment).where(Payment.id == payment_id))
        ).scalar_one()


# ── Preconditions ──────────────────────────────────────────────────────────
async def test_rejects_when_env_key_unset(Session, monkeypatch):
    monkeypatch.setattr(settings, "nostr_seckey", "")
    tenant, payment_id = await _seed(Session)
    with pytest.raises(HTTPException) as exc:
        await _sign(Session, tenant, payment_id)
    assert exc.value.status_code == 422
    assert "ORCHESTRATOR_NOSTR_SECKEY" in exc.value.detail


async def test_rejects_invalid_env_key_without_echoing_it(Session, monkeypatch):
    monkeypatch.setattr(settings, "nostr_seckey", "feedface" * 7)  # 56 chars
    tenant, payment_id = await _seed(Session)
    with pytest.raises(HTTPException) as exc:
        await _sign(Session, tenant, payment_id)
    assert exc.value.status_code == 422
    assert "feedface" not in exc.value.detail


async def test_rejects_when_tenant_pubkey_not_configured(Session, signing_env):
    tenant, payment_id = await _seed(Session, nostr_pubkey=None)
    with pytest.raises(HTTPException) as exc:
        await _sign(Session, tenant, payment_id)
    assert exc.value.status_code == 422
    assert "Settings" in exc.value.detail


async def test_rejects_key_pubkey_mismatch(Session, signing_env):
    tenant, payment_id = await _seed(Session, nostr_pubkey="ab" * 32)
    with pytest.raises(HTTPException) as exc:
        await _sign(Session, tenant, payment_id)
    assert exc.value.status_code == 409
    assert "does not match" in exc.value.detail


async def test_rejects_unpaid_payment(Session, signing_env):
    tenant, payment_id = await _seed(Session, payment_status="in_progress")
    with pytest.raises(HTTPException) as exc:
        await _sign(Session, tenant, payment_id)
    assert exc.value.status_code == 409
    assert "paid" in exc.value.detail


async def test_other_tenants_payment_is_invisible(Session, signing_env):
    _, payment_id = await _seed(Session)
    other, _ = await _seed(Session)
    with pytest.raises(HTTPException) as exc:
        await _sign(Session, other, payment_id)
    assert exc.value.status_code == 404


# ── Happy path ─────────────────────────────────────────────────────────────
async def test_sign_persists_verbatim_event_that_verifies_independently(
    Session, signing_env
):
    tenant, payment_id = await _seed(Session)
    result = await _sign(Session, tenant, payment_id)

    event = json.loads(result.event_json)
    assert result.event_id == event["id"]
    assert result.pubkey == PUBKEY_HEX
    assert result.npub.startswith("npub1")
    assert result.kind == OPENSPLIT_PROOF_KIND
    assert result.created_at == int(PAID_AT.timestamp())

    # Content is exactly the canonical bundle for this payment.
    payment = await _stored_payment(Session, payment_id)
    async with Session() as s:
        splits = (
            (
                await s.execute(
                    select(PaymentSplit, SplitTarget)
                    .join(SplitTarget, PaymentSplit.split_target_id == SplitTarget.id)
                    .where(PaymentSplit.payment_id == payment_id)
                )
            ).all()
        )

    class R:
        def __init__(self, split, target):
            self.label = target.label
            self.ln_address = target.ln_address
            self.amount_sats = split.amount_sats
            self.ln_payment_hash = split.ln_payment_hash
            self.ln_preimage = split.ln_preimage

    expected_bundle = canonical_proof_bundle(
        payment_id=payment_id,
        amount_sats=21001,
        rule_fingerprint=FINGERPRINT,
        splits=[R(sp, t) for sp, t in splits],
        timestamp=int(PAID_AT.timestamp()),
    )
    assert event["content"] == expected_bundle

    # Persisted verbatim: stored bytes are exactly what the API returned.
    assert payment.nostr_proof_event == result.event_json

    # Independent verification (spec NIP-01 id + pure-Python BIP-340).
    assert independent_event_id(event) == event["id"]
    assert schnorr_verify(
        bytes.fromhex(event["id"]),
        bytes.fromhex(event["pubkey"]),
        bytes.fromhex(event["sig"]),
    )


async def test_sign_never_leaks_the_private_key(Session, signing_env):
    tenant, payment_id = await _seed(Session)
    result = await _sign(Session, tenant, payment_id)
    payment = await _stored_payment(Session, payment_id)
    for haystack in (result.event_json, result.model_dump_json(), payment.nostr_proof_event):
        assert SECKEY_HEX not in haystack.lower()


async def test_sign_leaves_money_state_untouched(Session, signing_env):
    tenant, payment_id = await _seed(Session)

    async def snapshot():
        async with Session() as s:
            payment = (
                await s.execute(select(Payment).where(Payment.id == payment_id))
            ).scalar_one()
            splits = (
                (
                    await s.execute(
                        select(PaymentSplit)
                        .where(PaymentSplit.payment_id == payment_id)
                        .order_by(PaymentSplit.amount_sats)
                    )
                )
                .scalars()
                .all()
            )
        return (
            payment.status,
            payment.amount_sats,
            payment.paid_at,
            payment.unallocated_store_sats,
            payment.pending_remainder_sats,
            [(sp.status, sp.amount_sats, sp.btcpay_payout_id) for sp in splits],
        )

    before = await snapshot()
    await _sign(Session, tenant, payment_id)
    assert await snapshot() == before


async def test_payment_missing_fingerprint_and_preimages_signs_with_nulls(
    Session, signing_env
):
    tenant, payment_id = await _seed(Session, with_proof_columns=False)
    result = await _sign(Session, tenant, payment_id)
    bundle = json.loads(json.loads(result.event_json)["content"])
    assert bundle["rule_fingerprint"] is None
    assert all(s["ln_preimage"] is None for s in bundle["splits"])
    assert all(s["ln_payment_hash"] is None for s in bundle["splits"])
    # Honest nulls, but still a real signature over real amounts.
    event = json.loads(result.event_json)
    assert schnorr_verify(
        bytes.fromhex(event["id"]),
        bytes.fromhex(event["pubkey"]),
        bytes.fromhex(event["sig"]),
    )


# ── Idempotency ────────────────────────────────────────────────────────────
async def test_resign_of_unchanged_payment_returns_stored_event(Session, signing_env):
    tenant, payment_id = await _seed(Session)
    first = await _sign(Session, tenant, payment_id)
    stored_first = (await _stored_payment(Session, payment_id)).nostr_proof_event

    second = await _sign(Session, tenant, payment_id)
    stored_second = (await _stored_payment(Session, payment_id)).nostr_proof_event

    assert second.event_id == first.event_id
    assert second.event_json == first.event_json
    assert stored_second == stored_first  # byte-identical, not re-signed


async def test_resign_after_preimage_backfill_replaces_cleanly(Session, signing_env):
    tenant, payment_id = await _seed(Session)
    first = await _sign(Session, tenant, payment_id)

    # Reconciliation later backfills Dave's settlement proof (see 016 flows).
    async with Session() as s:
        dave_split = (
            await s.execute(
                select(PaymentSplit).where(
                    PaymentSplit.payment_id == payment_id,
                    PaymentSplit.amount_sats == 7000,
                )
            )
        ).scalar_one()
        dave_split.ln_preimage = "dd" * 32
        dave_split.ln_payment_hash = "ee" * 32
        await s.commit()

    second = await _sign(Session, tenant, payment_id)
    assert second.event_id != first.event_id
    bundle = json.loads(json.loads(second.event_json)["content"])
    dave = [s for s in bundle["splits"] if s["member"] == "Dave"][0]
    assert dave["ln_preimage"] == "dd" * 32

    # Replaced, not duplicated: the single column holds only the new event,
    # and it still verifies independently.
    stored = (await _stored_payment(Session, payment_id)).nostr_proof_event
    assert stored == second.event_json
    event = json.loads(stored)
    assert independent_event_id(event) == event["id"]
    assert schnorr_verify(
        bytes.fromhex(event["id"]),
        bytes.fromhex(event["pubkey"]),
        bytes.fromhex(event["sig"]),
    )


# ── GET /proof surfaces the stored event ───────────────────────────────────
async def test_get_proof_carries_nostr_proof_only_once_signed(Session, signing_env):
    tenant, payment_id = await _seed(Session)

    async with Session() as s:
        before = await get_split_proof(
            payment_id, current_user=None, tenant=tenant, session=s
        )
    assert before.nostr_proof is None

    signed = await _sign(Session, tenant, payment_id)
    async with Session() as s:
        after = await get_split_proof(
            payment_id, current_user=None, tenant=tenant, session=s
        )
    assert after.nostr_proof is not None
    assert after.nostr_proof.event_id == signed.event_id
    assert after.nostr_proof.event_json == signed.event_json
    assert after.nostr_proof.npub == signed.npub
