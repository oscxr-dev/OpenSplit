"""Multiple split rules may be active at once (each surfaces as a board tab).

Covers the behaviour added for the multi-active-rule tabs feature:
  * activating a second rule does NOT deactivate the first
  * an active rule cannot be deleted (must be deactivated first)
  * an inactive rule without payment history can be deleted
  * deactivating a rule clears its active flag so it can then be deleted

Runs against the dedicated ``orchestrator_test`` Postgres database; no real
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

from app.config import settings
from app.models import Base, SplitRule, SplitTarget, Tenant
from app.routers.splits import activate_split, deactivate_split, delete_split, update_split_public_visibility
from app.schemas import SplitRulePublicUpdate

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


async def _seed_rule(Session, tenant: Tenant, name: str, version: int = 1) -> uuid.UUID:
    """Inactive rule with two valid ln-address targets (60/40)."""
    rule_id = uuid.uuid4()
    async with Session() as s:
        rule = SplitRule(id=rule_id, tenant_id=tenant.id, name=name, active=False, version=version)
        s.add(rule)
        await s.flush()
        s.add(SplitTarget(split_rule_id=rule.id, label="Alice", ln_address="alice@x.com", percentage=60, order=0))
        s.add(SplitTarget(split_rule_id=rule.id, label="Bob", ln_address="bob@x.com", percentage=40, order=1))
        await s.commit()
    return rule_id


async def _is_active(Session, rule_id: uuid.UUID) -> bool:
    async with Session() as s:
        return (
            await s.execute(select(SplitRule.active).where(SplitRule.id == rule_id))
        ).scalar_one()


async def _is_public(Session, rule_id: uuid.UUID) -> bool:
    async with Session() as s:
        return (
            await s.execute(select(SplitRule.public_enabled).where(SplitRule.id == rule_id))
        ).scalar_one()


async def _exists(Session, rule_id: uuid.UUID) -> bool:
    async with Session() as s:
        return (
            await s.execute(select(SplitRule.id).where(SplitRule.id == rule_id))
        ).scalar_one_or_none() is not None


async def test_multiple_rules_can_be_active_at_once(Session):
    tenant = await _seed_tenant(Session)
    rule_a = await _seed_rule(Session, tenant, "Alpha")
    rule_b = await _seed_rule(Session, tenant, "Beta")

    async with Session() as s:
        await activate_split(str(rule_a), current_user=None, tenant=tenant, session=s)
    async with Session() as s:
        await activate_split(str(rule_b), current_user=None, tenant=tenant, session=s)

    # Activating Beta must NOT have deactivated Alpha.
    assert await _is_active(Session, rule_a) is True
    assert await _is_active(Session, rule_b) is True


async def test_public_toggle_is_per_rule_and_independent_from_active(Session):
    tenant = await _seed_tenant(Session)
    rule_a = await _seed_rule(Session, tenant, "Carol Dave")
    rule_b = await _seed_rule(Session, tenant, "BitCrew")

    async with Session() as s:
        await activate_split(str(rule_b), current_user=None, tenant=tenant, session=s)

    async with Session() as s:
        await update_split_public_visibility(
            str(rule_a),
            SplitRulePublicUpdate(public_enabled=True),
            current_user=None,
            tenant=tenant,
            session=s,
        )

    assert await _is_public(Session, rule_a) is True
    assert await _is_public(Session, rule_b) is False
    assert await _is_active(Session, rule_a) is False
    assert await _is_active(Session, rule_b) is True


async def test_activate_again_after_deactivating_all_rules(Session):
    """Regression: with every rule inactive, activating any rule must succeed and
    mark it active (the Team-board "activate after deactivating all" flow)."""
    tenant = await _seed_tenant(Session)
    rule_a = await _seed_rule(Session, tenant, "Alpha")
    rule_b = await _seed_rule(Session, tenant, "Beta")

    # Activate both, then deactivate everything -> all inactive.
    for rid in (rule_a, rule_b):
        async with Session() as s:
            await activate_split(str(rid), current_user=None, tenant=tenant, session=s)
    for rid in (rule_a, rule_b):
        async with Session() as s:
            await deactivate_split(str(rid), current_user=None, tenant=tenant, session=s)
    assert await _is_active(Session, rule_a) is False
    assert await _is_active(Session, rule_b) is False

    # Activating one again from the all-inactive state succeeds.
    async with Session() as s:
        result = await activate_split(str(rule_a), current_user=None, tenant=tenant, session=s)
    assert result.active is True
    assert await _is_active(Session, rule_a) is True

    # And a second rule can still be activated alongside it.
    async with Session() as s:
        await activate_split(str(rule_b), current_user=None, tenant=tenant, session=s)
    assert await _is_active(Session, rule_a) is True
    assert await _is_active(Session, rule_b) is True


async def test_deleting_an_active_rule_is_blocked(Session):
    tenant = await _seed_tenant(Session)
    rule_id = await _seed_rule(Session, tenant, "Alpha")

    async with Session() as s:
        await activate_split(str(rule_id), current_user=None, tenant=tenant, session=s)

    with pytest.raises(HTTPException) as exc:
        async with Session() as s:
            await delete_split(str(rule_id), current_user=None, tenant=tenant, session=s)

    assert exc.value.status_code == 409
    assert await _exists(Session, rule_id) is True


async def test_inactive_rule_without_history_can_be_deleted(Session):
    tenant = await _seed_tenant(Session)
    rule_id = await _seed_rule(Session, tenant, "Alpha")

    async with Session() as s:
        await delete_split(str(rule_id), current_user=None, tenant=tenant, session=s)

    assert await _exists(Session, rule_id) is False


async def test_deactivating_a_rule_allows_deletion(Session):
    tenant = await _seed_tenant(Session)
    rule_id = await _seed_rule(Session, tenant, "Alpha")

    async with Session() as s:
        await activate_split(str(rule_id), current_user=None, tenant=tenant, session=s)
    assert await _is_active(Session, rule_id) is True

    async with Session() as s:
        await deactivate_split(str(rule_id), current_user=None, tenant=tenant, session=s)
    assert await _is_active(Session, rule_id) is False

    # Once deactivated (its tab disappears) the rule deletes normally.
    async with Session() as s:
        await delete_split(str(rule_id), current_user=None, tenant=tenant, session=s)
    assert await _exists(Session, rule_id) is False
