"""GET /public-teams — discovery list of opt-in public teams.

Only public_transparency_enabled + active tenants with a slug appear, and the
response carries privacy-safe METADATA only (counts/timestamps), never money.

Runs against the dedicated orchestrator_test Postgres database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.routers.public import list_public_teams, public_transparency
from app.schemas import PublicTeamSummary

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


async def _make_tenant(s, *, name, slug, enabled, active=True, country=None, city=None) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name=name,
        adapter_type="btcpay",
        btcpay_url="https://btcpay.test",
        btcpay_api_key="k",
        btcpay_store_id="store-1",
        public_slug=slug,
        public_transparency_enabled=enabled,
        public_country=country,
        public_city=city,
        active=active,
    )
    s.add(t)
    return t


async def _seed(Session):
    async with Session() as s:
        # Public team with 1 active rule, a paid payment and 2 completed splits.
        a = await _make_tenant(s, name="Alpha", slug="alpha", enabled=True, country="Spain", city="Madrid")
        await s.flush()
        rule = SplitRule(tenant_id=a.id, name="r", active=True, public_enabled=True, version=1)
        s.add(rule)
        await s.flush()
        tgt = SplitTarget(split_rule_id=rule.id, label="X", ln_address="x@x.com", percentage=100, order=0)
        s.add(tgt)
        pay = Payment(
            id=uuid.uuid4(), tenant_id=a.id, invoice_id="inv-a", bolt11="lnbc",
            amount_sats=10_000, status="paid", paid_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        s.add(pay)
        await s.flush()
        s.add(PaymentSplit(payment_id=pay.id, split_target_id=tgt.id, amount_sats=6000, status="completed"))
        s.add(PaymentSplit(payment_id=pay.id, split_target_id=tgt.id, amount_sats=4000, status="completed"))

        # Disabled public page -> must NOT appear.
        await _make_tenant(s, name="Beta", slug="beta", enabled=False)
        # Enabled but no slug -> must NOT appear.
        await _make_tenant(s, name="Gamma", slug=None, enabled=True)
        await s.commit()


async def test_lists_only_enabled_public_teams_with_slug(Session):
    await _seed(Session)
    async with Session() as s:
        resp = await list_public_teams(session=s)

    slugs = [team.slug for team in resp.teams]
    assert slugs == ["alpha"]  # beta (disabled) and gamma (no slug) excluded


async def test_returns_privacy_safe_metadata_only(Session):
    await _seed(Session)
    async with Session() as s:
        resp = await list_public_teams(session=s)

    team = resp.teams[0]
    assert team.name == "Alpha"
    assert team.active_rule_count == 1
    assert team.completed_splits == 2
    assert team.country == "Spain" and team.city == "Madrid"
    assert team.last_activity is not None

    # The schema must not carry any money/volume fields.
    fields = set(PublicTeamSummary.model_fields)
    forbidden = {"amount_sats", "total_sats", "fiat", "balance", "sats", "volume", "ln_address"}
    assert fields.isdisjoint(forbidden), fields


async def test_empty_when_no_public_teams(Session):
    # No tenants seeded at all.
    async with Session() as s:
        resp = await list_public_teams(session=s)
    assert resp.teams == []


async def test_public_page_uses_public_enabled_not_active(Session):
    async with Session() as s:
        tenant = await _make_tenant(s, name="Alpha", slug="alpha", enabled=True)
        await s.flush()

        active_private = SplitRule(
            tenant_id=tenant.id,
            name="Private active rule",
            active=True,
            public_enabled=False,
            version=1,
        )
        public_inactive = SplitRule(
            tenant_id=tenant.id,
            name="Public inactive rule",
            active=False,
            public_enabled=True,
            version=2,
        )
        s.add_all([active_private, public_inactive])
        await s.flush()
        s.add_all(
            [
                SplitTarget(
                    split_rule_id=active_private.id,
                    label="Hidden",
                    ln_address="hidden@example.com",
                    percentage=100,
                    order=0,
                ),
                SplitTarget(
                    split_rule_id=public_inactive.id,
                    label="Visible",
                    ln_address="visible@example.com",
                    percentage=100,
                    order=0,
                ),
            ]
        )
        await s.commit()

    async with Session() as s:
        resp = await public_transparency(slug="alpha", session=s)

    assert [rule.name for rule in resp.public_rules] == ["Public inactive rule"]
    assert [member.label for member in resp.distribution] == ["Visible"]


async def test_multiple_public_rules_are_explicitly_listed(Session):
    async with Session() as s:
        tenant = await _make_tenant(s, name="Alpha", slug="alpha", enabled=True)
        await s.flush()
        rules = [
            SplitRule(tenant_id=tenant.id, name="Carol Dave", active=False, public_enabled=True, version=1),
            SplitRule(tenant_id=tenant.id, name="Team Ops", active=True, public_enabled=True, version=2),
            SplitRule(tenant_id=tenant.id, name="Private", active=True, public_enabled=False, version=3),
        ]
        s.add_all(rules)
        await s.flush()
        for rule in rules:
            s.add(SplitTarget(split_rule_id=rule.id, label=rule.name, ln_address="safe@example.com", percentage=100, order=0))
        await s.commit()

    async with Session() as s:
        resp = await public_transparency(slug="alpha", session=s)

    names = {rule.name for rule in resp.public_rules}
    assert names == {"Carol Dave", "Team Ops"}
    assert "Private" not in names
