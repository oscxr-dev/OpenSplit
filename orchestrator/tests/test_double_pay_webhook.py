"""Concurrency guards for webhook payment processing.

Runs against Postgres (the guarantees are DB-level) on a dedicated
orchestrator_test database; no real Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.routers.webhooks as webhooks_mod
import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, SplitRule, SplitTarget, Tenant
from app.routers.webhooks import btcpay_webhook
from app.services.split_engine import SplitEngine

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

TIMEOUT = 10.0


@pytest_asyncio.fixture
async def engine():
    # NullPool gives each session its own connection so two can run concurrently.
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


async def _seed_tenant_rule(Session) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Acme-{tenant_id.hex[:8]}",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.test",
            btcpay_api_key="test-key",
            btcpay_store_id="store-1",
            btcpay_webhook_secret="test-webhook-secret",  # required; sig check is faked below
            active=True,
        )
        rule = SplitRule(tenant_id=tenant_id, name="Default", active=True, version=1)
        s.add_all([tenant, rule])
        await s.flush()
        s.add(
            SplitTarget(
                split_rule_id=rule.id,
                label="Alice",
                ln_address="alice@example.com",
                percentage=100,
                order=0,
            )
        )
        await s.commit()
        return tenant_id, rule.id


class PayoutSpy:
    # First call parks so the second processor runs while the first is mid-flight.
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.first_in = asyncio.Event()
        self.release = asyncio.Event()

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        self.calls.append((ln_address, amount_sats))
        if len(self.calls) == 1:
            self.first_in.set()
            await self.release.wait()
        return {"id": f"payout-{len(self.calls)}"}

    async def close(self):
        pass


class FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers: dict[str, str] = {}

    async def body(self) -> bytes:
        return self._body


async def test_concurrent_processing_pays_invoice_once(Session):
    """Two concurrent runs over the same payment send exactly one payout."""
    tenant_id, _ = await _seed_tenant_rule(Session)

    invoice_id = "inv-race-a"
    payment_id = uuid.uuid4()
    async with Session() as s:
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                bolt11="lnbc-test",
                amount_sats=10_000,
                status="pending",
            )
        )
        await s.commit()

    split_mod.load_lnd_receiver = lambda label: None  # force the ln_address branch

    spy = PayoutSpy()
    session_a = Session()
    session_b = Session()
    try:
        engine_a = SplitEngine(session_a, lnbits_client=None)
        engine_b = SplitEngine(session_b, lnbits_client=None)

        task_a = asyncio.create_task(engine_a.execute_splits_btcpay(payment_id, spy))
        await asyncio.wait_for(spy.first_in.wait(), TIMEOUT)

        await asyncio.wait_for(
            engine_b.execute_splits_btcpay(payment_id, spy), TIMEOUT
        )

        spy.release.set()
        await asyncio.wait_for(task_a, TIMEOUT)
    finally:
        await session_a.close()
        await session_b.close()

    assert len(spy.calls) == 1, f"expected 1 payout, got {len(spy.calls)}: {spy.calls}"


async def test_concurrent_pos_webhooks_create_single_payment(Session, monkeypatch):
    """Two concurrent POS webhooks for one invoice create exactly one payment."""
    tenant_id, _ = await _seed_tenant_rule(Session)
    invoice_id = "inv-pos-b"

    payout_calls: list[tuple[str, int]] = []
    first_fetch_in = asyncio.Event()
    release = asyncio.Event()

    class FakeBTCPay:
        _get_invoice_calls = 0

        def __init__(self, base_url=None, api_key=None, store_id=None):
            pass

        async def get_invoice(self, invoice):
            FakeBTCPay._get_invoice_calls += 1
            # First handler parks after its lookup so the second runs concurrently.
            if FakeBTCPay._get_invoice_calls == 1:
                first_fetch_in.set()
                await release.wait()
            return {"amount": "10000", "currency": "SATS"}

        async def get_invoice_payment_methods(self, invoice):
            return [
                {
                    "paymentMethodId": "BTC-LightningNetwork",
                    "currency": "BTC",
                    "paymentMethodPaid": "0.00010000",
                }
            ]

        async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
            payout_calls.append((ln_address, amount_sats))
            return {"id": f"payout-{len(payout_calls)}"}

        async def close(self):
            pass

        @classmethod
        def verify_webhook_sig(cls, secret, body, sig):
            return True

    monkeypatch.setattr(webhooks_mod, "BTCPayClient", FakeBTCPay)
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)

    body = json.dumps(
        {"type": "InvoiceSettled", "invoiceId": invoice_id, "metadata": {}}
    ).encode()

    session_a = Session()
    session_b = Session()
    try:
        task_a = asyncio.create_task(
            btcpay_webhook(tenant_id=tenant_id, request=FakeRequest(body), session=session_a)
        )
        await asyncio.wait_for(first_fetch_in.wait(), TIMEOUT)

        await asyncio.wait_for(
            btcpay_webhook(tenant_id=tenant_id, request=FakeRequest(body), session=session_b),
            TIMEOUT,
        )

        release.set()
        await asyncio.wait_for(task_a, TIMEOUT)
    finally:
        await session_a.close()
        await session_b.close()

    async with Session() as s:
        count = (
            await s.execute(
                select(func.count())
                .select_from(Payment)
                .where(Payment.invoice_id == invoice_id)
            )
        ).scalar_one()

    assert count == 1, f"expected 1 payment row, got {count}"
