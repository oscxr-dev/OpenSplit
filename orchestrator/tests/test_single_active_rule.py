"""Exactly one split rule may be active per tenant (the processing rule).

Replaces the multi-active "board tabs" behaviour: the engine always paid with a
single rule, so the API and database now enforce that invariant outright.

Covers:
  * activating a rule deactivates the previously active one atomically
  * re-activating the already-active rule keeps it active (no-op)
  * the supersede guard still blocks re-activating an older version of the
    active lineage (409) without touching the current active rule
  * the partial unique index rejects a second active rule at the DB level
  * tenants keep independent active rules
  * editing an active rule hands the active flag to the new version without
    ever holding two active rows (index-safe flush order)
  * the delete/deactivate lifecycle is unchanged
  * the migration's dedupe statement keeps exactly the rule the engine pays with

Runs against the dedicated ``orchestrator_test`` Postgres database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base, SplitRule, SplitTarget, Tenant
from app.routers.splits import (
    activate_split,
    deactivate_split,
    delete_split,
    update_split,
    update_split_public_visibility,
)
from app.schemas import SplitRulePublicUpdate, SplitRuleUpdate, SplitTargetCreate

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

_INDEX_NAME = "uq_split_rules_one_active_per_tenant"
_CREATE_INDEX_SQL = f"CREATE UNIQUE INDEX {_INDEX_NAME} ON split_rules (tenant_id) WHERE active"

# The exact dedupe statement migration 013 runs, loaded from the migration file
# itself so this test cannot drift from what upgrade() executes.
_MIGRATION_FILE = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "013_single_active_rule.py"
)
_spec = importlib.util.spec_from_file_location("migration_013_single_active_rule", _MIGRATION_FILE)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
DEDUPE_ACTIVE_RULES_SQL = _migration.DEDUPE_ACTIVE_RULES_SQL


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


async def _seed_rule(
    Session, tenant: Tenant, name: str, version: int = 1, active: bool = False
) -> uuid.UUID:
    """Rule with two valid ln-address targets (60/40)."""
    rule_id = uuid.uuid4()
    async with Session() as s:
        rule = SplitRule(id=rule_id, tenant_id=tenant.id, name=name, active=active, version=version)
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


async def _active_rule_ids(Session, tenant_id: uuid.UUID) -> set[uuid.UUID]:
    async with Session() as s:
        return set(
            (
                await s.execute(
                    select(SplitRule.id).where(
                        SplitRule.tenant_id == tenant_id,
                        SplitRule.active == True,  # noqa: E712
                    )
                )
            ).scalars().all()
        )


# ── Activation replaces the previous active rule ─────────────────────────


async def test_activating_second_rule_deactivates_first(Session):
    tenant = await _seed_tenant(Session)
    rule_a = await _seed_rule(Session, tenant, "Alpha")
    rule_b = await _seed_rule(Session, tenant, "Beta")

    async with Session() as s:
        await activate_split(str(rule_a), current_user=None, tenant=tenant, session=s)
    async with Session() as s:
        await activate_split(str(rule_b), current_user=None, tenant=tenant, session=s)

    assert await _is_active(Session, rule_a) is False
    assert await _is_active(Session, rule_b) is True
    assert await _active_rule_ids(Session, tenant.id) == {rule_b}


async def test_reactivating_the_active_rule_keeps_it_active(Session):
    tenant = await _seed_tenant(Session)
    rule_id = await _seed_rule(Session, tenant, "Alpha")

    for _ in range(2):
        async with Session() as s:
            result = await activate_split(str(rule_id), current_user=None, tenant=tenant, session=s)
        assert result.active is True

    assert await _active_rule_ids(Session, tenant.id) == {rule_id}


async def test_activating_different_lineage_replaces_active_lineage(Session):
    tenant = await _seed_tenant(Session)
    menu_v2 = await _seed_rule(Session, tenant, "Menu", version=2, active=True)
    tips_v1 = await _seed_rule(Session, tenant, "Tips", version=1)

    async with Session() as s:
        await activate_split(str(tips_v1), current_user=None, tenant=tenant, session=s)

    assert await _is_active(Session, menu_v2) is False
    assert await _active_rule_ids(Session, tenant.id) == {tips_v1}


async def test_older_version_of_active_lineage_is_still_blocked(Session):
    tenant = await _seed_tenant(Session)
    menu_v1 = await _seed_rule(Session, tenant, "Menu", version=1)
    menu_v2 = await _seed_rule(Session, tenant, "Menu", version=2, active=True)

    with pytest.raises(HTTPException) as exc:
        async with Session() as s:
            await activate_split(str(menu_v1), current_user=None, tenant=tenant, session=s)

    assert exc.value.status_code == 409
    # The newest version keeps processing payments, untouched by the attempt.
    assert await _is_active(Session, menu_v2) is True
    assert await _active_rule_ids(Session, tenant.id) == {menu_v2}


async def test_activate_again_after_deactivating_all_rules(Session):
    """With every rule inactive, activating any rule succeeds; activating a
    second one afterwards replaces it (never runs alongside)."""
    tenant = await _seed_tenant(Session)
    rule_a = await _seed_rule(Session, tenant, "Alpha")
    rule_b = await _seed_rule(Session, tenant, "Beta")

    async with Session() as s:
        await activate_split(str(rule_a), current_user=None, tenant=tenant, session=s)
    async with Session() as s:
        await deactivate_split(str(rule_a), current_user=None, tenant=tenant, session=s)
    assert await _active_rule_ids(Session, tenant.id) == set()

    async with Session() as s:
        result = await activate_split(str(rule_a), current_user=None, tenant=tenant, session=s)
    assert result.active is True

    async with Session() as s:
        await activate_split(str(rule_b), current_user=None, tenant=tenant, session=s)
    assert await _active_rule_ids(Session, tenant.id) == {rule_b}


# ── The invariant itself ──────────────────────────────────────────────────


async def test_db_rejects_a_second_active_rule_per_tenant(Session):
    tenant = await _seed_tenant(Session)
    await _seed_rule(Session, tenant, "Alpha", active=True)

    with pytest.raises(IntegrityError):
        await _seed_rule(Session, tenant, "Beta", active=True)

    assert len(await _active_rule_ids(Session, tenant.id)) == 1


async def test_each_tenant_keeps_its_own_active_rule(Session):
    tenant_a = await _seed_tenant(Session)
    tenant_b = await _seed_tenant(Session)
    rule_a = await _seed_rule(Session, tenant_a, "Alpha", active=True)
    rule_b = await _seed_rule(Session, tenant_b, "Beta", active=True)

    assert await _active_rule_ids(Session, tenant_a.id) == {rule_a}
    assert await _active_rule_ids(Session, tenant_b.id) == {rule_b}


async def test_editing_active_rule_moves_active_flag_to_new_version(Session):
    """update_split inserts the successor while the old version is still in the
    same transaction — the handover must never trip the partial unique index."""
    tenant = await _seed_tenant(Session)
    rule_id = await _seed_rule(Session, tenant, "Team split", active=True)

    async with Session() as s:
        updated = await update_split(
            str(rule_id),
            SplitRuleUpdate(
                targets=[
                    SplitTargetCreate(label="Alice", ln_address="alice@x.com", percentage=50, order=0),
                    SplitTargetCreate(label="Bob", ln_address="bob@x.com", percentage=50, order=1),
                ]
            ),
            current_user=None,
            tenant=tenant,
            session=s,
        )

    assert updated.version == 2
    assert updated.active is True
    assert await _is_active(Session, rule_id) is False
    assert await _active_rule_ids(Session, tenant.id) == {updated.id}


# ── Public toggle stays independent from active ───────────────────────────


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


# ── Delete lifecycle is unchanged ─────────────────────────────────────────


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

    async with Session() as s:
        await delete_split(str(rule_id), current_user=None, tenant=tenant, session=s)
    assert await _exists(Session, rule_id) is False


# ── Migration dedupe matches the engine's rule selection ──────────────────


async def test_migration_dedupe_keeps_the_rule_the_engine_pays_with(engine, Session):
    # Recreate the pre-migration world: index gone, several active rules.
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP INDEX {_INDEX_NAME}"))

    tenant = await _seed_tenant(Session)
    other_tenant = await _seed_tenant(Session)
    now = datetime.now(timezone.utc)

    legacy = uuid.uuid4()          # lowest version, oldest
    stale_v3 = uuid.uuid4()        # same version as survivor, older created_at
    survivor = uuid.uuid4()        # highest version + newest created_at
    solo = uuid.uuid4()            # other tenant's only active rule
    async with Session() as s:
        s.add_all(
            [
                SplitRule(id=legacy, tenant_id=tenant.id, name="Legacy", active=True,
                          version=1, created_at=now - timedelta(days=2)),
                SplitRule(id=stale_v3, tenant_id=tenant.id, name="Stale", active=True,
                          version=3, created_at=now - timedelta(days=1)),
                SplitRule(id=survivor, tenant_id=tenant.id, name="Polar Carol Dave 50/50",
                          active=True, version=3, created_at=now - timedelta(hours=1)),
                SplitRule(id=solo, tenant_id=other_tenant.id, name="Solo", active=True,
                          version=1, created_at=now),
            ]
        )
        await s.commit()

    # What the split engine pays with today: version DESC, created_at DESC.
    async with Session() as s:
        engine_pick = (
            await s.execute(
                select(SplitRule.id)
                .where(SplitRule.tenant_id == tenant.id, SplitRule.active == True)  # noqa: E712
                .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
            )
        ).scalars().first()
    assert engine_pick == survivor

    async with engine.begin() as conn:
        await conn.execute(text(DEDUPE_ACTIVE_RULES_SQL))

    # Only the engine's pick survives; single-active tenants are untouched.
    assert await _active_rule_ids(Session, tenant.id) == {survivor}
    assert await _active_rule_ids(Session, other_tenant.id) == {solo}

    # The deduped data satisfies the constraint the migration adds next.
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_INDEX_SQL))
