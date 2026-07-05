"""Editing a public split rule keeps the public page on the newest version (P2).

When the public rule is edited, the new version must inherit public_enabled,
carry the incremented version number, and replace the old version on
GET /public/{slug}. The old version must stop being publicly visible.

Runs against the dedicated ``orchestrator_test`` Postgres database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base, SplitRule, SplitTarget, Tenant
from app.routers.public import public_transparency
from app.routers.splits import update_split
from app.schemas import SplitRuleUpdate, SplitTargetCreate

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


async def _seed_public_tenant(Session) -> Tenant:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Acme",
        adapter_type="btcpay",
        btcpay_url="https://btcpay.test",
        btcpay_api_key="k",
        btcpay_store_id="store-1",
        public_slug="acme",
        public_transparency_enabled=True,
        active=True,
    )
    async with Session() as s:
        s.add(tenant)
        await s.commit()
    return tenant


async def _seed_public_rule(Session, tenant: Tenant) -> uuid.UUID:
    """Public rule v1 with distribution A: Alice 60 / Bob 40."""
    rule_id = uuid.uuid4()
    async with Session() as s:
        rule = SplitRule(
            id=rule_id, tenant_id=tenant.id, name="Team split",
            active=True, public_enabled=True, version=1,
        )
        s.add(rule)
        await s.flush()
        s.add(SplitTarget(split_rule_id=rule.id, label="Alice", ln_address="alice@x.com", percentage=60, order=0))
        s.add(SplitTarget(split_rule_id=rule.id, label="Bob", ln_address="bob@x.com", percentage=40, order=1))
        await s.commit()
    return rule_id


# Distribution B: Alice 30 / Bob 70.
_UPDATE_B = SplitRuleUpdate(
    targets=[
        SplitTargetCreate(label="Alice", ln_address="alice@x.com", percentage=30, order=0),
        SplitTargetCreate(label="Bob", ln_address="bob@x.com", percentage=70, order=1),
    ]
)


async def test_editing_public_rule_carries_public_flag_to_new_version(Session):
    tenant = await _seed_public_tenant(Session)
    old_id = await _seed_public_rule(Session, tenant)

    async with Session() as s:
        updated = await update_split(
            str(old_id), _UPDATE_B, current_user=None, tenant=tenant, session=s
        )

    assert updated.version == 2
    assert updated.public_enabled is True

    async with Session() as s:
        old_public, new_public = (
            (await s.execute(select(SplitRule.public_enabled).where(SplitRule.id == old_id))).scalar_one(),
            (await s.execute(select(SplitRule.public_enabled).where(SplitRule.id == updated.id))).scalar_one(),
        )
    assert old_public is False
    assert new_public is True


async def test_public_page_shows_edited_version_and_distribution(Session):
    tenant = await _seed_public_tenant(Session)
    old_id = await _seed_public_rule(Session, tenant)

    async with Session() as s:
        await update_split(str(old_id), _UPDATE_B, current_user=None, tenant=tenant, session=s)

    async with Session() as s:
        view = await public_transparency(slug="acme", session=s)

    # Only the edited version is public, at the incremented version number.
    assert len(view.public_rules) == 1
    rule = view.public_rules[0]
    assert rule.version == 2
    assert {(m.label, m.percentage) for m in rule.distribution} == {("Alice", 30.0), ("Bob", 70.0)}
    # Distribution B replaced distribution A everywhere on the page.
    assert {(m.label, m.percentage) for m in view.distribution} == {("Alice", 30.0), ("Bob", 70.0)}


async def test_editing_non_public_rule_stays_non_public(Session):
    tenant = await _seed_public_tenant(Session)
    rule_id = uuid.uuid4()
    async with Session() as s:
        rule = SplitRule(id=rule_id, tenant_id=tenant.id, name="Private split", active=False, version=1)
        s.add(rule)
        await s.flush()
        s.add(SplitTarget(split_rule_id=rule.id, label="Alice", ln_address="alice@x.com", percentage=100, order=0))
        await s.commit()

    async with Session() as s:
        updated = await update_split(
            str(rule_id), _UPDATE_B, current_user=None, tenant=tenant, session=s
        )

    assert updated.version == 2
    assert updated.public_enabled is False

    async with Session() as s:
        view = await public_transparency(slug="acme", session=s)
    assert view.public_rules == []


async def test_amount_privacy_unchanged_after_edit(Session):
    """Step 2 privacy: editing the public rule must not surface amounts."""
    tenant = await _seed_public_tenant(Session)
    old_id = await _seed_public_rule(Session, tenant)

    async with Session() as s:
        await update_split(str(old_id), _UPDATE_B, current_user=None, tenant=tenant, session=s)

    async with Session() as s:
        view = await public_transparency(slug="acme", session=s)

    assert view.show_amounts is False
    assert view.total_sats is None
    assert all(p.amount_sats is None for p in view.recent_payments)
