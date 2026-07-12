"""Rule fingerprint is captured at payment freeze time and stored verbatim.

Both freeze points — the LNbits record_split path and the BTCPay
execute_splits_btcpay claim — must stamp payments.rule_fingerprint in the same
commit that sets split_rule_id, computed over ALL of the frozen rule's stored
targets (including 0% shares). A later change to the rule tables must never
change what a past payment carries.

Runs against Postgres on the dedicated orchestrator_test database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, SplitRule, SplitTarget, Tenant
from app.services.proof_hash import rule_fingerprint
from app.services.split_engine import SplitEngine

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

AMOUNT_SATS = 10_000


class OkBTCPay:
    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        return {"id": f"payout-{ln_address}"}

    async def close(self):
        pass


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


async def _seed(Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Tenant + one active rule (60/40 + a 0% target) + one pending payment.

    The 0% target is deliberate: the allocation loop skips it, but the
    fingerprint must still cover it — it is part of the stored rule version.
    """
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Fingerprint-{tenant_id.hex[:8]}",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.test",
            btcpay_api_key="test-key",
            btcpay_store_id="store-1",
            btcpay_webhook_secret="test-webhook-secret",
            active=True,
        )
        rule = SplitRule(tenant_id=tenant_id, name="Fingerprint", active=True, version=1)
        s.add_all([tenant, rule])
        await s.flush()
        s.add_all(
            [
                SplitTarget(
                    split_rule_id=rule.id,
                    label="Alice",
                    ln_address="alice@example.com",
                    percentage=60,
                    order=0,
                ),
                SplitTarget(
                    split_rule_id=rule.id,
                    label="Bob",
                    ln_address="bob@example.com",
                    percentage=40,
                    order=1,
                ),
                SplitTarget(
                    split_rule_id=rule.id,
                    label="Dormant",
                    ln_address="dormant@example.com",
                    percentage=0,
                    order=2,
                ),
            ]
        )
        payment_id = uuid.uuid4()
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant_id,
                invoice_id=f"inv-{payment_id.hex[:8]}",
                bolt11="lnbc-test",
                amount_sats=AMOUNT_SATS,
                status="pending",
            )
        )
        await s.commit()
        rule_id = rule.id
    return tenant_id, rule_id, payment_id


async def _expected_fingerprint(Session, rule_id) -> str:
    async with Session() as s:
        rule = (
            await s.execute(select(SplitRule).where(SplitRule.id == rule_id))
        ).scalar_one()
        targets = list(
            (
                await s.execute(
                    select(SplitTarget)
                    .where(SplitTarget.split_rule_id == rule_id)
                    .order_by(SplitTarget.order)
                )
            ).scalars()
        )
    assert len(targets) == 3  # includes the 0% target
    return rule_fingerprint(rule, targets)


async def _stored_payment(Session, payment_id) -> Payment:
    async with Session() as s:
        return (
            await s.execute(select(Payment).where(Payment.id == payment_id))
        ).scalar_one()


async def test_btcpay_freeze_stamps_fingerprint_over_all_targets(Session, monkeypatch):
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    _, rule_id, payment_id = await _seed(Session)
    expected = await _expected_fingerprint(Session, rule_id)

    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(
            payment_id, OkBTCPay()
        )

    payment = await _stored_payment(Session, payment_id)
    assert payment.split_rule_id == rule_id
    assert payment.rule_fingerprint == expected


async def test_lnbits_record_split_stamps_fingerprint(Session):
    _, rule_id, payment_id = await _seed(Session)
    expected = await _expected_fingerprint(Session, rule_id)

    async with Session() as s:
        await SplitEngine(s).record_split(payment_id)

    payment = await _stored_payment(Session, payment_id)
    assert payment.split_rule_id == rule_id
    assert payment.rule_fingerprint == expected


async def test_stored_fingerprint_survives_later_rule_edits(Session, monkeypatch):
    """The column is a verbatim capture: mutating the rule tables afterwards
    (which app flows never do to a frozen version, but the DB could) must not
    change what the payment carries."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    _, rule_id, payment_id = await _seed(Session)
    expected = await _expected_fingerprint(Session, rule_id)

    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(
            payment_id, OkBTCPay()
        )

    async with Session() as s:
        alice = (
            await s.execute(
                select(SplitTarget).where(
                    SplitTarget.split_rule_id == rule_id, SplitTarget.label == "Alice"
                )
            )
        ).scalar_one()
        alice.percentage = 61
        await s.commit()

    payment = await _stored_payment(Session, payment_id)
    assert payment.rule_fingerprint == expected


async def test_old_payment_without_fingerprint_stays_null(Session):
    """Pre-existing paid payments are not backfilled."""
    tenant_id, _, _ = await _seed(Session)
    old_id = uuid.uuid4()
    async with Session() as s:
        s.add(
            Payment(
                id=old_id,
                tenant_id=tenant_id,
                invoice_id=f"inv-{old_id.hex[:8]}",
                bolt11="lnbc-old",
                amount_sats=500,
                status="paid",
            )
        )
        await s.commit()

    payment = await _stored_payment(Session, old_id)
    assert payment.rule_fingerprint is None
