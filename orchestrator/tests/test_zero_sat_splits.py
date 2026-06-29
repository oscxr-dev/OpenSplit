"""A split that rounds to 0 sats must not trigger a payout or a lying status.

Runs against Postgres on a dedicated orchestrator_test database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.payout_reconciliation as recon_mod
import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.services.payout_reconciliation import reconcile_tenant_payouts
from app.services.split_engine import SplitEngine

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

# 1 sat over five equal targets is too small to pay only one winner.
EQUAL_FIFTHS = [20, 20, 20, 20, 20]


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


class ZeroRejectingBTCPay:
    """Mimics BTCPay: a payout of 0 sats is rejected."""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        self.calls.append((ln_address, amount_sats))
        if amount_sats <= 0:
            raise RuntimeError("payout amount must be positive")
        return {"id": f"payout-{ln_address}"}

    async def close(self):
        pass


class ReconCompleted:
    def __init__(self, base_url="", api_key="", store_id=""):
        pass

    async def get_payout(self, payout_id):
        return {"state": "Completed"}

    async def close(self):
        pass


async def _seed(Session, percentages, amount_sats, adapter="btcpay"):
    tenant_id, payment_id = uuid.uuid4(), uuid.uuid4()
    async with Session() as s:
        s.add(
            Tenant(
                id=tenant_id,
                name=f"Acme-{tenant_id.hex[:8]}",
                adapter_type=adapter,
                btcpay_url="https://btcpay.test",
                btcpay_api_key="k",
                btcpay_store_id="store-1",
                btcpay_webhook_secret=None,
                active=True,
            )
        )
        rule = SplitRule(tenant_id=tenant_id, name="rule", active=True, version=1)
        s.add(rule)
        await s.flush()
        for i, p in enumerate(percentages):
            s.add(SplitTarget(split_rule_id=rule.id, label=f"M{i}", ln_address=f"m{i}@x.com", percentage=p, order=i))
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant_id,
                invoice_id=f"inv-{payment_id.hex[:8]}",
                bolt11="lnbc",
                amount_sats=amount_sats,
                status="pending",
            )
        )
        await s.commit()
    return tenant_id, payment_id


async def _split_states(Session, payment_id) -> list[tuple[int, str]]:
    async with Session() as s:
        rows = (
            await s.execute(
                select(PaymentSplit.amount_sats, PaymentSplit.status)
                .where(PaymentSplit.payment_id == payment_id)
            )
        ).all()
    return [(amount, status) for amount, status in rows]


async def _payment_status(Session, payment_id) -> str:
    async with Session() as s:
        return (await s.execute(select(Payment.status).where(Payment.id == payment_id))).scalar_one()


async def _payment_remainder(Session, payment_id) -> int:
    async with Session() as s:
        return (
            await s.execute(select(Payment.pending_remainder_sats).where(Payment.id == payment_id))
        ).scalar_one()


async def test_btcpay_zero_sat_split_is_skipped_not_failed(Session, monkeypatch):
    """0-sat splits are skipped (no payout attempt, no failed/completed)."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    tenant_id, payment_id = await _seed(Session, EQUAL_FIFTHS, amount_sats=1)

    btcpay = ZeroRejectingBTCPay()
    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(payment_id, btcpay)

    assert btcpay.calls == []

    states = await _split_states(Session, payment_id)
    skipped = [amt for amt, st in states if st == "skipped"]
    failed = [amt for amt, st in states if st == "failed"]
    assert failed == [], f"0-sat splits left as failed: {states}"
    assert len(skipped) == 5 and all(amt == 0 for amt in skipped), states
    assert await _payment_remainder(Session, payment_id) == 1

    # No payout was fair/payable; the dust stays as pending treasury remainder.
    monkeypatch.setattr(recon_mod, "BTCPayClient", ReconCompleted)
    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    assert await _payment_status(Session, payment_id) == "paid"


async def test_lnbits_zero_sat_split_not_marked_completed(Session):
    """0-sat splits are skipped, not falsely marked completed."""
    tenant_id, payment_id = await _seed(Session, EQUAL_FIFTHS, amount_sats=1, adapter="lnbits")

    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).record_split(payment_id)

    states = await _split_states(Session, payment_id)
    completed = [amt for amt, st in states if st == "completed"]
    skipped = [amt for amt, st in states if st == "skipped"]
    assert completed == []
    assert len(skipped) == 5 and all(amt == 0 for amt in skipped), states
    assert await _payment_remainder(Session, payment_id) == 1

    assert await _payment_status(Session, payment_id) == "paid"
