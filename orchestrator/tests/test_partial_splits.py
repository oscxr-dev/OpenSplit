"""Partial split rules: a rule may total <= 100%. Only the configured targets
are paid; the unallocated remainder stays in the store (no payout, no fake
target). Also checks the activation guard accepts <100% and rejects >100%.

Runs against the dedicated orchestrator_test Postgres database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.routers.splits import activate_split, delete_split
from app.services.split_engine import SplitEngine

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"


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


class OkBTCPay:
    """Records every payout it is asked to send."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        self.calls.append((ln_address, amount_sats))
        return {"id": f"payout-{ln_address}"}

    async def close(self):
        pass


async def _seed_tenant(Session) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=f"Acme-{uuid.uuid4().hex[:8]}",
        adapter_type="btcpay",
        btcpay_url="https://btcpay.test",
        btcpay_api_key="k",
        btcpay_store_id="store-1",
        btcpay_webhook_secret=None,
        active=True,
    )
    async with Session() as s:
        s.add(tenant)
        await s.commit()
    return tenant


async def _seed_partial_rule_payment(Session, tenant: Tenant, percentages, amount_sats=10_000):
    rule_id, payment_id = uuid.uuid4(), uuid.uuid4()
    async with Session() as s:
        s.add(SplitRule(id=rule_id, tenant_id=tenant.id, name="partial", active=True, version=1))
        await s.flush()
        for i, p in enumerate(percentages):
            s.add(SplitTarget(split_rule_id=rule_id, label=f"M{i}", ln_address=f"m{i}@x.com", percentage=p, order=i))
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant.id,
                invoice_id=f"inv-{payment_id.hex[:8]}",
                bolt11="lnbc",
                amount_sats=amount_sats,
                status="pending",
            )
        )
        await s.commit()
    return rule_id, payment_id


async def test_partial_rule_pays_only_configured_targets(Session, monkeypatch):
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    tenant = await _seed_tenant(Session)
    # 20 / 20 / 20 = 60% of 10_000 = 6_000 paid out; 4_000 stays in store.
    _, payment_id = await _seed_partial_rule_payment(Session, tenant, [20, 20, 20], amount_sats=10_000)

    btcpay = OkBTCPay()
    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(payment_id, btcpay)

    async with Session() as s:
        rows = (
            await s.execute(select(PaymentSplit.amount_sats).where(PaymentSplit.payment_id == payment_id))
        ).scalars().all()
        payment = (await s.execute(select(Payment).where(Payment.id == payment_id))).scalar_one()

    # One split per configured target — no fabricated "store" target.
    assert sorted(rows) == [2000, 2000, 2000]
    assert sum(rows) == 6000
    # Exactly the three configured payouts were sent, totalling the 60% share.
    assert len(btcpay.calls) == 3
    assert sum(amount for _, amount in btcpay.calls) == 6000
    # The unallocated 40% (4_000 sats) was never paid out.
    assert 10_000 - sum(rows) == 4000
    assert payment.unallocated_store_sats == 4000
    assert payment.pending_remainder_sats == 0


async def test_indivisible_partial_remainder_is_persisted(Session):
    tenant = await _seed_tenant(Session)
    _, payment_id = await _seed_partial_rule_payment(Session, tenant, [20, 20, 20], amount_sats=1)

    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).record_split(payment_id)

    async with Session() as s:
        payment = (await s.execute(select(Payment).where(Payment.id == payment_id))).scalar_one()
        rows = (
            await s.execute(select(PaymentSplit.amount_sats).where(PaymentSplit.payment_id == payment_id))
        ).scalars().all()

    assert rows == [0, 0, 0]
    assert payment.unallocated_store_sats == 0
    assert payment.pending_remainder_sats == 1


async def test_rule_changes_do_not_mutate_old_payment_remainders(Session):
    tenant = await _seed_tenant(Session)
    old_rule_id, payment_id = await _seed_partial_rule_payment(Session, tenant, [20, 20, 20], amount_sats=1)

    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).record_split(payment_id)

    async with Session() as s:
        payment_before = (await s.execute(select(Payment).where(Payment.id == payment_id))).scalar_one()
        original = (
            payment_before.split_rule_id,
            payment_before.unallocated_store_sats,
            payment_before.pending_remainder_sats,
        )

    new_rule_id = uuid.uuid4()
    deletable_rule_id = uuid.uuid4()
    async with Session() as s:
        s.add(SplitRule(id=new_rule_id, tenant_id=tenant.id, name="new", active=False, version=1))
        s.add(SplitRule(id=deletable_rule_id, tenant_id=tenant.id, name="temp", active=False, version=1))
        await s.flush()
        s.add(SplitTarget(split_rule_id=new_rule_id, label="N0", ln_address="n0@x.com", percentage=100, order=0))
        s.add(SplitTarget(split_rule_id=deletable_rule_id, label="D0", ln_address="d0@x.com", percentage=100, order=0))
        await s.commit()

    async with Session() as s:
        await activate_split(str(new_rule_id), current_user=None, tenant=tenant, session=s)

    with pytest.raises(HTTPException):
        async with Session() as s:
            await delete_split(str(old_rule_id), current_user=None, tenant=tenant, session=s)

    async with Session() as s:
        await delete_split(str(deletable_rule_id), current_user=None, tenant=tenant, session=s)

    async with Session() as s:
        payment_after = (await s.execute(select(Payment).where(Payment.id == payment_id))).scalar_one()
        rows = (
            await s.execute(select(PaymentSplit.amount_sats).where(PaymentSplit.payment_id == payment_id))
        ).scalars().all()

    assert (
        payment_after.split_rule_id,
        payment_after.unallocated_store_sats,
        payment_after.pending_remainder_sats,
    ) == original
    assert rows == [0, 0, 0]


async def test_activation_accepts_partial_and_rejects_over_100(Session):
    tenant = await _seed_tenant(Session)

    partial_id, _ = await _seed_partial_rule_payment(Session, tenant, [25, 25])  # 50%
    async with Session() as s:
        result = await activate_split(str(partial_id), current_user=None, tenant=tenant, session=s)
    assert result.active is True

    over_id, _ = await _seed_partial_rule_payment(Session, tenant, [70, 70])  # 140%
    with pytest.raises(HTTPException) as exc:
        async with Session() as s:
            await activate_split(str(over_id), current_user=None, tenant=tenant, session=s)
    assert exc.value.status_code == 422
