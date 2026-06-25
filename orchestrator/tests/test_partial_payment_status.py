"""Parent payment status must reflect whether every split actually paid.

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


async def _seed(Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Tenant + active rule with two ln-address targets (Alice 60 / Bob 40)."""
    tenant_id = uuid.uuid4()
    payment_id = uuid.uuid4()
    async with Session() as s:
        s.add(
            Tenant(
                id=tenant_id,
                name=f"Acme-{tenant_id.hex[:8]}",
                adapter_type="btcpay",
                btcpay_url="https://btcpay.test",
                btcpay_api_key="k",
                btcpay_store_id="store-1",
                btcpay_webhook_secret=None,
                active=True,
            )
        )
        rule = SplitRule(tenant_id=tenant_id, name="Default", active=True, version=1)
        s.add(rule)
        await s.flush()
        s.add(SplitTarget(split_rule_id=rule.id, label="Alice", ln_address="alice@x.com", percentage=60, order=0))
        s.add(SplitTarget(split_rule_id=rule.id, label="Bob", ln_address="bob@x.com", percentage=40, order=1))
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant_id,
                invoice_id=f"inv-{payment_id.hex[:8]}",
                bolt11="lnbc",
                amount_sats=10_000,
                status="pending",
            )
        )
        await s.commit()
    return tenant_id, payment_id


class BTCPayStub:
    """Payout succeeds for everyone except `fail_addr`, which raises."""

    def __init__(self, fail_addr: str | None = None):
        self.fail_addr = fail_addr
        self.calls: list[tuple[str, int]] = []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        self.calls.append((ln_address, amount_sats))
        if ln_address == self.fail_addr:
            raise RuntimeError("no route to destination")
        return {"id": f"payout-{ln_address}"}

    async def close(self):
        pass


async def _split_status_by_label(Session, payment_id) -> dict[str, str]:
    async with Session() as s:
        rows = (
            await s.execute(
                select(SplitTarget.label, PaymentSplit.status)
                .join(PaymentSplit, PaymentSplit.split_target_id == SplitTarget.id)
                .where(PaymentSplit.payment_id == payment_id)
            )
        ).all()
    return {label: status for label, status in rows}


async def _payment_status(Session, payment_id) -> str:
    async with Session() as s:
        return (
            await s.execute(select(Payment.status).where(Payment.id == payment_id))
        ).scalar_one()


async def test_payment_not_marked_paid_when_a_payout_fails(Session, monkeypatch):
    """A payment with a failed split must not report 'paid'."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    tenant_id, payment_id = await _seed(Session)

    btcpay = BTCPayStub(fail_addr="bob@x.com")
    async with Session() as s:
        engine = SplitEngine(s, lnbits_client=None)
        await engine.execute_splits_btcpay(payment_id, btcpay)

    status = await _payment_status(Session, payment_id)
    splits = await _split_status_by_label(Session, payment_id)

    assert splits["Bob"] == "failed", splits
    assert splits["Alice"] == "in_progress", splits
    assert status != "paid", f"payment reported 'paid' with a failed split: {splits}"
    assert status == "partial", f"expected 'partial', got {status!r}"


async def test_settled_payment_is_partial_when_one_split_failed(Session, monkeypatch):
    """After confirmation, a payment with one failed split settles to 'partial',
    the delivered split to 'completed', and the failed split stays 'failed'."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    tenant_id, payment_id = await _seed(Session)

    btcpay = BTCPayStub(fail_addr="bob@x.com")
    async with Session() as s:
        engine = SplitEngine(s, lnbits_client=None)
        await engine.execute_splits_btcpay(payment_id, btcpay)

    class ReconClient:
        def __init__(self, base_url="", api_key="", store_id=""):
            pass

        async def get_payout(self, payout_id):
            return {"state": "Completed"}  # Alice's in_progress payout confirms

        async def close(self):
            pass

    monkeypatch.setattr(recon_mod, "BTCPayClient", ReconClient)

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    status = await _payment_status(Session, payment_id)
    splits = await _split_status_by_label(Session, payment_id)

    assert splits["Alice"] == "completed", splits
    assert splits["Bob"] == "failed", splits
    assert status == "partial", f"expected 'partial', got {status!r}"
