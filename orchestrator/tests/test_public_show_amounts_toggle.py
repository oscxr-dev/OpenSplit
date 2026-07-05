"""PATCH /tenants/me exposes public_show_amounts (PR 8).

The amount-visibility preference is DB-backed but must be togglable entirely
through the tenant API — no SQL. These tests cover the PATCH round-trip (on/off,
omitted = unchanged, standard PATCH semantics), that TenantResponse surfaces the
saved value so the UI can reflect it, and that exposing this NON-secret field
never loosens the redaction contract (api key / webhook secret stay absent).

Runs against the dedicated orchestrator_test Postgres database.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base, Tenant
from app.routers.tenants import update_my_tenant
from app.schemas import TenantUpdate

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

RAW_KEY = "sk-live-verysecret-btcpay-key-9F3A"
WEBHOOK_SECRET = "whsec-super-secret-webhook-value"


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


async def _seed_tenant(Session) -> uuid.UUID:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=f"Acme-{uuid.uuid4().hex[:8]}",
        adapter_type="btcpay",
        btcpay_url="https://btcpay.local",
        btcpay_api_key=RAW_KEY,
        btcpay_store_id="store-1",
        btcpay_webhook_secret=WEBHOOK_SECRET,
        active=True,
    )
    async with Session() as s:
        s.add(tenant)
        await s.commit()
    return tenant.id


async def _get_tenant(session, tenant_id: uuid.UUID) -> Tenant:
    return (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one()


async def test_default_is_false(Session):
    tenant_id = await _seed_tenant(Session)
    async with Session() as s:
        stored = await _get_tenant(s, tenant_id)
    assert stored.public_show_amounts is False


async def test_patch_toggles_on_then_off(Session):
    tenant_id = await _seed_tenant(Session)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp_on = await update_my_tenant(
            TenantUpdate(public_show_amounts=True),
            current_user=None,
            tenant=tenant,
            session=s,
        )
    assert resp_on.public_show_amounts is True
    async with Session() as s:
        assert (await _get_tenant(s, tenant_id)).public_show_amounts is True

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp_off = await update_my_tenant(
            TenantUpdate(public_show_amounts=False),
            current_user=None,
            tenant=tenant,
            session=s,
        )
    assert resp_off.public_show_amounts is False
    async with Session() as s:
        assert (await _get_tenant(s, tenant_id)).public_show_amounts is False


async def test_patch_omitted_leaves_value_unchanged(Session):
    tenant_id = await _seed_tenant(Session)

    # Opt in, then run an unrelated PATCH that omits public_show_amounts.
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        await update_my_tenant(
            TenantUpdate(public_show_amounts=True),
            current_user=None,
            tenant=tenant,
            session=s,
        )
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        await update_my_tenant(
            TenantUpdate(name="Renamed"),
            current_user=None,
            tenant=tenant,
            session=s,
        )

    async with Session() as s:
        stored = await _get_tenant(s, tenant_id)
        assert stored.name == "Renamed"
        assert stored.public_show_amounts is True  # omitted PATCH never flipped it


async def test_response_exposes_flag_without_leaking_secrets(Session):
    """public_show_amounts is safe to expose; the raw key/secret never are."""
    tenant_id = await _seed_tenant(Session)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await update_my_tenant(
            TenantUpdate(public_show_amounts=True),
            current_user=None,
            tenant=tenant,
            session=s,
        )

    body = resp.model_dump_json()
    assert '"public_show_amounts":true' in body
    assert '"btcpay_api_key":' not in body
    assert '"btcpay_webhook_secret":' not in body
    assert RAW_KEY not in body
    assert WEBHOOK_SECRET not in body
