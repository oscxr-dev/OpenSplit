from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.payout_reconciliation as reconciliation_mod
from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.services.payout_reconciliation import (
    map_btcpay_payout_state,
    payout_failure_reason,
    reconcile_tenant_payouts,
)

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"


def test_btcpay_payout_state_mapping():
    assert map_btcpay_payout_state("AwaitingApproval") == "in_progress"
    assert map_btcpay_payout_state("AwaitingPayment") == "in_progress"
    assert map_btcpay_payout_state("InProgress") == "in_progress"
    assert map_btcpay_payout_state("Completed") == "completed"
    assert map_btcpay_payout_state("Cancelled") == "failed"


def test_unknown_btcpay_state_stays_non_terminal():
    assert map_btcpay_payout_state("UnexpectedFutureState") == "in_progress"


def test_failure_reason_handles_different_btcpay_shapes():
    assert payout_failure_reason(
        {"paymentProof": {"error": "No route found"}}, "Cancelled"
    ) == "No route found"
    assert payout_failure_reason(
        {"paymentProof": "opaque-proof"}, "Cancelled"
    ) == "BTCPay reportó el payout como Cancelled."


# ── Raw payout state persistence (DB-backed) ───────────────────────────────


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


class FakePayoutClient:
    """Returns a preset payout dict for get_payout; records nothing else."""

    def __init__(self, payout: dict, **kwargs):
        self._payout = payout

    async def get_payout(self, payout_id: str) -> dict:
        return self._payout

    async def close(self) -> None:
        pass


async def _seed_split_with_payout(Session, *, payout_id: str = "payout-1") -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Acme-{uuid.uuid4().hex[:8]}",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.local",
            btcpay_api_key="k",
            btcpay_store_id="store-1",
            active=True,
        )
        s.add(tenant)
        rule = SplitRule(tenant_id=tenant_id, name="Default", active=True, version=1)
        s.add(rule)
        await s.flush()
        target = SplitTarget(
            split_rule_id=rule.id, label="Alice", ln_address="alice@example.com",
            percentage=100, order=0,
        )
        s.add(target)
        payment = Payment(
            tenant_id=tenant_id, invoice_id="inv-1", amount_sats=10_000,
            status="in_progress", split_rule_id=rule.id,
        )
        s.add(payment)
        await s.flush()
        split = PaymentSplit(
            payment_id=payment.id, split_target_id=target.id, amount_sats=10_000,
            btcpay_payout_id=payout_id, status="in_progress",
        )
        s.add(split)
        await s.commit()
        return tenant_id, split.id


@pytest.mark.parametrize(
    "state,expected_status",
    [
        ("AwaitingApproval", "in_progress"),
        ("AwaitingPayment", "in_progress"),
        ("InProgress", "in_progress"),
        ("Completed", "completed"),
        ("Cancelled", "failed"),
    ],
)
@pytest.mark.asyncio
async def test_reconciliation_persists_raw_state(Session, monkeypatch, state, expected_status):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient({"id": "payout-1", "state": state}),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        # Raw state stored verbatim; mapped status unchanged from the mapping.
        assert split.btcpay_payout_state == state
        assert split.status == expected_status


@pytest.mark.asyncio
async def test_reconciliation_stores_none_when_state_absent(Session, monkeypatch):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient({"id": "payout-1"}),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        assert split.btcpay_payout_state is None
