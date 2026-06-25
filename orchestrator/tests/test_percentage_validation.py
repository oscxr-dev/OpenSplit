"""A split rule the API accepts must always be processable at payout time.

Runs against Postgres on a dedicated orchestrator_test database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, SplitRule, SplitTarget, Tenant
from app.schemas import SplitRuleCreate, SplitTargetCreate
from app.services.split_engine import SplitEngine

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

# Raw float sum is ~100 (passes the API's tolerance), but at the stored 2-decimal
# precision each rounds to 33.33, summing to 99.99 — which calculate_splits rejects.
PROBLEM_PCTS = [33.334, 33.333, 33.333]
VALID_PCTS = [33.34, 33.33, 33.33]


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
    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        return {"id": f"payout-{ln_address}"}

    async def close(self):
        pass


def _api_accepts(percentages) -> bool:
    try:
        SplitRuleCreate(
            name="rule",
            targets=[
                SplitTargetCreate(label=f"M{i}", ln_address=f"m{i}@x.com", percentage=p, order=i)
                for i, p in enumerate(percentages)
            ],
        )
        return True
    except ValidationError:
        return False


async def _seed_rule_payment(Session, percentages) -> uuid.UUID:
    tenant_id, payment_id = uuid.uuid4(), uuid.uuid4()
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
                amount_sats=10_000,
                status="pending",
            )
        )
        await s.commit()
    return payment_id


async def test_api_accepted_rule_always_processes(Session, monkeypatch):
    """If the API accepts a rule, a payment with it must process without error."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)

    api_ok = _api_accepts(PROBLEM_PCTS)
    payment_id = await _seed_rule_payment(Session, PROBLEM_PCTS)

    raised: str | None = None
    async with Session() as s:
        try:
            await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(payment_id, OkBTCPay())
        except ValueError as exc:
            raised = str(exc)

    assert not api_ok or raised is None, (
        f"API accepted the rule but processing raised: {raised}"
    )


async def test_valid_rule_is_accepted_and_processes(Session, monkeypatch):
    """A rule whose 2-decimal percentages sum to 100 is accepted and processes."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)

    assert _api_accepts(VALID_PCTS)
    payment_id = await _seed_rule_payment(Session, VALID_PCTS)

    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(payment_id, OkBTCPay())

    async with Session() as s:
        status = (await s.execute(select(Payment.status).where(Payment.id == payment_id))).scalar_one()
    assert status != "pending"
