"""Aggregate pipeline status — GET /tenants/me/status (PR 4).

Covers the pure decision helpers with frozen thresholds, plus the endpoint
itself against the dedicated ``orchestrator_test`` Postgres database for the
key scenarios: unconfigured tenant, fully-verified pipeline, a payout waiting
in BTCPay >3min, and a recent failure. Read-only — no BTCPay calls are made
except a mocked reachability ping.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.routers.tenants as tenants_mod
from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.routers.tenants import (
    SplitDeliveryFact,
    compute_lightning_payout_processor,
    compute_payout_delivery,
    compute_store_status,
    compute_webhook_status,
    get_tenant_status,
)

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


# ── Pure helpers ────────────────────────────────────────────────────────────


def test_store_status_transitions():
    assert compute_store_status(configured=False, reachable=None) == "not_configured"
    assert compute_store_status(configured=True, reachable=True) == "ok"
    assert compute_store_status(configured=True, reachable=False) == "unreachable"


def test_webhook_status_transitions():
    assert compute_webhook_status(secret_set=False, last_webhook_at=None) == "not_configured"
    assert compute_webhook_status(secret_set=True, last_webhook_at=None) == "waiting"
    assert compute_webhook_status(secret_set=True, last_webhook_at=NOW) == "verified"


def _fact(status, state=None, executed_at=None, updated_at=None):
    return SplitDeliveryFact(
        status=status, btcpay_payout_state=state,
        executed_at=executed_at, updated_at=updated_at,
    )


def test_payout_delivery_idle_when_no_outstanding_splits():
    assert compute_payout_delivery([], NOW) == "idle"
    assert compute_payout_delivery([_fact("completed")], NOW) == "idle"


def test_payout_delivery_delivering_for_fresh_in_flight():
    facts = [_fact("in_progress", executed_at=NOW - timedelta(seconds=30))]
    assert compute_payout_delivery(facts, NOW) == "delivering"


def test_payout_delivery_fresh_waiting_state_is_still_delivering():
    # AwaitingPayment but younger than 3 min → normal in-flight, not stuck.
    facts = [_fact("in_progress", state="AwaitingPayment", executed_at=NOW - timedelta(minutes=1))]
    assert compute_payout_delivery(facts, NOW) == "delivering"


def test_payout_delivery_waiting_in_btcpay_after_threshold():
    facts = [_fact("in_progress", state="AwaitingPayment", executed_at=NOW - timedelta(minutes=5))]
    assert compute_payout_delivery(facts, NOW) == "waiting_in_btcpay"
    facts = [_fact("in_progress", state="AwaitingApproval", executed_at=NOW - timedelta(minutes=5))]
    assert compute_payout_delivery(facts, NOW) == "waiting_in_btcpay"


def test_payout_delivery_recent_failure_outranks_waiting():
    facts = [
        _fact("in_progress", state="AwaitingPayment", executed_at=NOW - timedelta(minutes=5)),
        _fact("failed", updated_at=NOW - timedelta(hours=1)),
    ]
    assert compute_payout_delivery(facts, NOW) == "failing"


def test_payout_delivery_old_failure_does_not_count():
    facts = [_fact("failed", updated_at=NOW - timedelta(hours=25))]
    assert compute_payout_delivery(facts, NOW) == "idle"


def test_lightning_payout_processor_active():
    assert compute_lightning_payout_processor(
        [{"name": "Lightning", "payoutMethodId": "BTC-LightningNetwork"}]
    ) == "active"
    # Older builds key it as ``paymentMethod``.
    assert compute_lightning_payout_processor(
        [{"paymentMethod": "BTC-LightningNetwork"}]
    ) == "active"


def test_lightning_payout_processor_missing_when_empty_or_other_method():
    assert compute_lightning_payout_processor([]) == "missing"
    assert compute_lightning_payout_processor(
        [{"name": "OnChain", "payoutMethodId": "BTC-CHAIN"}]
    ) == "missing"


def test_lightning_payout_processor_unknown_when_none():
    # None = the list couldn't be read (permission/404/unreachable) — never guess.
    assert compute_lightning_payout_processor(None) == "unknown"


# ── Endpoint scenarios (DB-backed) ──────────────────────────────────────────


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


class FakePingClient:
    def __init__(self, reachable: bool, processors=None, **kwargs):
        self._reachable = reachable
        self._processors = processors

    async def ping(self) -> bool:
        return self._reachable

    async def get_payout_processors(self):
        return self._processors

    async def close(self) -> None:
        pass


def _mock_ping(monkeypatch, reachable: bool, processors=None):
    monkeypatch.setattr(
        tenants_mod,
        "BTCPayClient",
        lambda *a, **k: FakePingClient(reachable, processors=processors),
    )


async def _get_tenant(session, tenant_id):
    return (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()


async def _seed_tenant(Session, **fields) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    defaults = dict(
        id=tenant_id,
        name=f"Acme-{uuid.uuid4().hex[:8]}",
        adapter_type="btcpay",
        active=True,
    )
    defaults.update(fields)
    async with Session() as s:
        s.add(Tenant(**defaults))
        await s.commit()
    return tenant_id


async def _add_active_rule(Session, tenant_id, *, name="Weekend split", version=2):
    async with Session() as s:
        rule = SplitRule(tenant_id=tenant_id, name=name, active=True, version=version)
        s.add(rule)
        await s.flush()
        s.add(SplitTarget(split_rule_id=rule.id, label="Alice",
                          ln_address="alice@example.com", percentage=100, order=0))
        await s.commit()
        return rule.id


async def _add_split(Session, tenant_id, rule_id, *, status, state=None, executed_at=None):
    async with Session() as s:
        target = (await s.execute(
            select(SplitTarget).where(SplitTarget.split_rule_id == rule_id)
        )).scalars().first()
        payment = Payment(tenant_id=tenant_id, invoice_id=f"inv-{uuid.uuid4().hex[:8]}",
                          amount_sats=10_000, status="in_progress", split_rule_id=rule_id)
        s.add(payment)
        await s.flush()
        split = PaymentSplit(
            payment_id=payment.id, split_target_id=target.id, amount_sats=10_000,
            status=status, btcpay_payout_state=state,
            btcpay_payout_id="payout-x",
        )
        if executed_at is not None:
            split.executed_at = executed_at
        s.add(split)
        await s.commit()
        return split.id


@pytest.mark.asyncio
async def test_status_unconfigured_tenant(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session)
    _mock_ping(monkeypatch, True)  # never called: store not configured

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.store == "not_configured"
    assert resp.webhook == "not_configured"
    assert resp.active_rule is None
    assert resp.payout_delivery == "idle"
    assert resp.public_page == "off"


@pytest.mark.asyncio
async def test_status_verified_pipeline(Session, monkeypatch):
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local",
        btcpay_api_key="k",
        btcpay_store_id="store-1",
        btcpay_webhook_secret="s",
        last_webhook_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        public_transparency_enabled=True,
    )
    await _add_active_rule(Session, tenant_id, name="Weekend split", version=2)
    _mock_ping(monkeypatch, True)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.store == "ok"
    assert resp.webhook == "verified"
    assert resp.active_rule is not None
    assert resp.active_rule.name == "Weekend split"
    assert resp.active_rule.version == 2
    assert resp.payout_delivery == "idle"
    assert resp.public_page == "on"


@pytest.mark.asyncio
async def test_status_store_unreachable_and_webhook_waiting(Session, monkeypatch):
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local",
        btcpay_api_key="k",
        btcpay_store_id="store-1",
        btcpay_webhook_secret="s",
        last_webhook_at=None,
    )
    _mock_ping(monkeypatch, False)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.store == "unreachable"
    assert resp.webhook == "waiting"


@pytest.mark.asyncio
async def test_status_payout_waiting_in_btcpay(Session, monkeypatch):
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local", btcpay_api_key="k", btcpay_store_id="store-1",
    )
    rule_id = await _add_active_rule(Session, tenant_id)
    await _add_split(
        Session, tenant_id, rule_id, status="in_progress", state="AwaitingPayment",
        executed_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    _mock_ping(monkeypatch, True)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.payout_delivery == "waiting_in_btcpay"


@pytest.mark.asyncio
async def test_status_recent_failure(Session, monkeypatch):
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local", btcpay_api_key="k", btcpay_store_id="store-1",
    )
    rule_id = await _add_active_rule(Session, tenant_id)
    await _add_split(Session, tenant_id, rule_id, status="failed")
    _mock_ping(monkeypatch, True)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.payout_delivery == "failing"


@pytest.mark.asyncio
async def test_status_lightning_processor_active(Session, monkeypatch):
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local", btcpay_api_key="k", btcpay_store_id="store-1",
    )
    _mock_ping(
        monkeypatch, True,
        processors=[{"payoutMethodId": "BTC-LightningNetwork"}],
    )

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.store == "ok"
    assert resp.lightning_payout_processor == "active"


@pytest.mark.asyncio
async def test_status_lightning_processor_missing(Session, monkeypatch):
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local", btcpay_api_key="k", btcpay_store_id="store-1",
    )
    _mock_ping(monkeypatch, True, processors=[])

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.lightning_payout_processor == "missing"


@pytest.mark.asyncio
async def test_status_lightning_processor_unknown_when_unreadable(Session, monkeypatch):
    # Store reachable but the key can't read processors → None → "unknown".
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local", btcpay_api_key="k", btcpay_store_id="store-1",
    )
    _mock_ping(monkeypatch, True, processors=None)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.lightning_payout_processor == "unknown"


@pytest.mark.asyncio
async def test_status_lightning_processor_unknown_when_store_not_ok(Session, monkeypatch):
    # Never probe when the store is unreachable — stays "unknown".
    tenant_id = await _seed_tenant(
        Session,
        btcpay_url="https://btcpay.local", btcpay_api_key="k", btcpay_store_id="store-1",
    )
    _mock_ping(monkeypatch, False, processors=[{"payoutMethodId": "BTC-LightningNetwork"}])

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.store == "unreachable"
    assert resp.lightning_payout_processor == "unknown"


@pytest.mark.asyncio
async def test_status_lightning_processor_unknown_when_store_not_configured(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session)  # no BTCPay creds
    _mock_ping(monkeypatch, True)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await get_tenant_status(current_user=None, tenant=tenant, session=s)

    assert resp.store == "not_configured"
    assert resp.lightning_payout_processor == "unknown"
