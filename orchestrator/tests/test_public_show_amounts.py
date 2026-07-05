"""GET /public/{slug} — amounts are private by default (Public Privacy P1).

A tenant that never touched public_show_amounts must NOT leak total_sats or
per-payment amount_sats through the public transparency endpoint; amounts are
returned only after an explicit opt-in (public_show_amounts=True).

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
from app.models import Base, Payment, Tenant
from app.routers.public import public_transparency

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


async def _seed_tenant(Session, *, show_amounts: bool | None) -> None:
    """Seed one public tenant with a paid payment.

    show_amounts=None leaves the column untouched so the model default applies —
    exactly what every pre-existing tenant looks like after migration 012.
    """
    async with Session() as s:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Alpha",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.test",
            btcpay_api_key="k",
            btcpay_store_id="store-1",
            public_slug="alpha",
            public_transparency_enabled=True,
            active=True,
        )
        if show_amounts is not None:
            tenant.public_show_amounts = show_amounts
        s.add(tenant)
        await s.flush()
        s.add(
            Payment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                invoice_id="inv-a",
                bolt11="lnbc",
                amount_sats=10_000,
                status="paid",
                paid_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        )
        await s.commit()


async def test_amounts_hidden_by_default(Session):
    """A tenant that never opted in must not expose any sats amounts."""
    await _seed_tenant(Session, show_amounts=None)
    async with Session() as s:
        view = await public_transparency(slug="alpha", session=s)

    assert view.show_amounts is False
    assert view.total_sats is None
    assert len(view.recent_payments) == 1
    assert all(p.amount_sats is None for p in view.recent_payments)


async def test_amounts_hidden_when_explicitly_false(Session):
    await _seed_tenant(Session, show_amounts=False)
    async with Session() as s:
        view = await public_transparency(slug="alpha", session=s)

    assert view.show_amounts is False
    assert view.total_sats is None
    assert all(p.amount_sats is None for p in view.recent_payments)


async def test_amounts_returned_only_with_explicit_opt_in(Session):
    await _seed_tenant(Session, show_amounts=True)
    async with Session() as s:
        view = await public_transparency(slug="alpha", session=s)

    assert view.show_amounts is True
    assert view.total_sats == 10_000
    assert [p.amount_sats for p in view.recent_payments] == [10_000]
