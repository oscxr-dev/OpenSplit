"""BTCPay connection settings (PR 2): PATCH fields, redaction, probe, authorize.

Covers:
  * PATCH /tenants/me persists btcpay_url / btcpay_api_key / btcpay_store_id
    with normalization (trim, no trailing slash, http(s) scheme required)
  * blank or omitted fields never wipe stored values (PATCH semantics)
  * REDACTION CONTRACT: no tenant-facing response body ever contains the raw
    API key or the webhook secret — asserted on serialized JSON
  * POST /tenants/me/btcpay/test distinguishes unreachable URL, rejected key,
    missing store, and success (mocked httpx transport; read-only GET probe)
  * GET /tenants/me/btcpay/authorize-url builds the minimal permission set and
    422s until a server URL is saved

Runs against the dedicated ``orchestrator_test`` Postgres database; the only
HTTP traffic is through httpx.MockTransport.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.btcpay_client as btcpay_module
from app.config import settings
from app.models import Base, Tenant
from app.routers.tenants import (
    BTCPAY_MINIMAL_PERMISSIONS,
    get_btcpay_authorize_url,
    get_my_tenant,
    interpret_store_probe,
    btcpay_connection_test,
    update_my_tenant,
)
from app.schemas import TenantUpdate

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

RAW_KEY = "sk-live-verysecret-btcpay-key-9F3A"  # last4 = 9F3A
WEBHOOK_SECRET = "whsec-super-secret-webhook-value"
STORE_ID = "store-abc123"
SERVER_URL = "https://btcpay.local"


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


async def _seed_tenant(Session, *, configured: bool) -> uuid.UUID:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=f"Acme-{uuid.uuid4().hex[:8]}",
        adapter_type="btcpay",
        btcpay_url=SERVER_URL if configured else None,
        btcpay_api_key=RAW_KEY if configured else None,
        btcpay_store_id=STORE_ID if configured else None,
        btcpay_webhook_secret=WEBHOOK_SECRET if configured else None,
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


def _mock_btcpay_http(monkeypatch, handler):
    """Route every BTCPayClient request through an httpx.MockTransport."""
    real_async_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_async_client(
            transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout")
        )

    monkeypatch.setattr(btcpay_module.httpx, "AsyncClient", factory)


def _status_handler(code: int, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(code, json={"id": STORE_ID})

    return handler


# ── PATCH round-trip and normalization ─────────────────────────────────────


async def test_patch_persists_and_normalizes_btcpay_fields(Session):
    tenant_id = await _seed_tenant(Session, configured=False)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await update_my_tenant(
            TenantUpdate(
                btcpay_url="  https://btcpay.local/  ",
                btcpay_api_key=f"  {RAW_KEY}  ",
                btcpay_store_id=f"  {STORE_ID}  ",
            ),
            current_user=None,
            tenant=tenant,
            session=s,
        )

    async with Session() as s:
        stored = await _get_tenant(s, tenant_id)
        assert stored.btcpay_url == SERVER_URL  # trimmed, no trailing slash
        assert stored.btcpay_api_key == RAW_KEY
        assert stored.btcpay_store_id == STORE_ID

    assert resp.btcpay_url == SERVER_URL
    assert resp.btcpay_store_id == STORE_ID
    assert resp.btcpay_api_key_set is True
    assert resp.btcpay_api_key_last4 == "9F3A"


async def test_blank_or_omitted_fields_never_wipe_stored_values(Session):
    tenant_id = await _seed_tenant(Session, configured=True)

    # Omitted fields: unrelated PATCH leaves the connection untouched.
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        await update_my_tenant(
            TenantUpdate(name="Renamed"), current_user=None, tenant=tenant, session=s
        )

    # Blank fields: normalized to "not provided", still no wipe.
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        await update_my_tenant(
            TenantUpdate(btcpay_url="   ", btcpay_api_key="", btcpay_store_id="  "),
            current_user=None,
            tenant=tenant,
            session=s,
        )

    async with Session() as s:
        stored = await _get_tenant(s, tenant_id)
        assert stored.name == "Renamed"
        assert stored.btcpay_url == SERVER_URL
        assert stored.btcpay_api_key == RAW_KEY
        assert stored.btcpay_store_id == STORE_ID


def test_btcpay_url_requires_http_scheme():
    for bad in ("btcpay.local", "ftp://btcpay.local", "https:/oops"):
        with pytest.raises(ValidationError):
            TenantUpdate(btcpay_url=bad)
    # Scheme is case-insensitive and trailing slashes are stripped.
    assert TenantUpdate(btcpay_url="HTTPS://btcpay.local//").btcpay_url == "HTTPS://btcpay.local"


def test_btcpay_url_requires_full_hostname():
    # Truncated single-label hosts (the "http://h" bug) are rejected; the rule
    # mirrors dashboard/src/lib/browserUrl.ts (isValidServerUrl).
    for bad in ("http://h", "http://h:3003", "https://internal", "http://h/path"):
        with pytest.raises(ValidationError):
            TenantUpdate(btcpay_url=bad)
    for good in (
        "https://btcpay.example.com",
        "http://localhost:3003",
        "http://host.docker.internal:3003",
        "http://192.168.1.20:3003",
    ):
        assert TenantUpdate(btcpay_url=good).btcpay_url == good


def test_store_id_longer_than_column_is_rejected():
    with pytest.raises(ValidationError):
        TenantUpdate(btcpay_store_id="x" * 65)


# ── Redaction contract ─────────────────────────────────────────────────────


async def test_no_tenant_endpoint_serializes_key_or_secret(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session, configured=True)
    _mock_btcpay_http(monkeypatch, _status_handler(200))

    bodies: dict[str, str] = {}

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        health = await get_my_tenant(current_user=None, tenant=tenant)
        bodies["GET /tenants/me"] = health.model_dump_json()

        patched = await update_my_tenant(
            TenantUpdate(name="Still Acme"), current_user=None, tenant=tenant, session=s
        )
        bodies["PATCH /tenants/me"] = patched.model_dump_json()

        probe = await btcpay_connection_test(current_user=None, tenant=tenant)
        bodies["POST /tenants/me/btcpay/test"] = probe.model_dump_json()

        authorize = await get_btcpay_authorize_url(current_user=None, tenant=tenant)
        bodies["GET /tenants/me/btcpay/authorize-url"] = authorize.model_dump_json()

    for endpoint, body in bodies.items():
        assert RAW_KEY not in body, endpoint
        assert WEBHOOK_SECRET not in body, endpoint
        # The raw fields must not even exist as keys ( *_set / *_last4 are the
        # only allowed derivatives, hence the colon in the needle).
        assert '"btcpay_api_key":' not in body, endpoint
        assert '"btcpay_webhook_secret":' not in body, endpoint

    # Presence indicators are computed correctly.
    assert health.tenant.btcpay_api_key_set is True
    assert health.tenant.btcpay_api_key_last4 == "9F3A"
    assert health.connection_status == "ok"
    assert health.lnbits_status == "ok"  # legacy alias keeps the same value


async def test_short_keys_do_not_expose_a_last4(Session):
    tenant_id = await _seed_tenant(Session, configured=False)
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await update_my_tenant(
            TenantUpdate(btcpay_api_key="k123"), current_user=None, tenant=tenant, session=s
        )
    assert resp.btcpay_api_key_set is True
    assert resp.btcpay_api_key_last4 is None  # 4 chars would be the whole key


# ── Connection probe ───────────────────────────────────────────────────────


PROBE_CASES = [
    (200, {"url_reachable": True, "auth_ok": True, "store_found": True, "ok": True}),
    (401, {"url_reachable": True, "auth_ok": False, "store_found": None, "ok": False}),
    (403, {"url_reachable": True, "auth_ok": False, "store_found": None, "ok": False}),
    (404, {"url_reachable": True, "auth_ok": True, "store_found": False, "ok": False}),
    (500, {"url_reachable": True, "auth_ok": None, "store_found": None, "ok": False}),
]


@pytest.mark.parametrize("status_code,expected", PROBE_CASES)
async def test_probe_maps_http_status_to_granular_checks(
    Session, monkeypatch, status_code, expected
):
    tenant_id = await _seed_tenant(Session, configured=True)
    _mock_btcpay_http(monkeypatch, _status_handler(status_code))

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
    result = await btcpay_connection_test(current_user=None, tenant=tenant)

    assert result.model_dump(exclude={"detail"}) == expected
    assert result.detail  # always one actionable sentence
    assert RAW_KEY not in result.detail


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda req: httpx.ConnectError("connection refused", request=req),
        lambda req: httpx.ConnectTimeout("timed out", request=req),
        lambda req: httpx.ReadTimeout("timed out", request=req),
    ],
)
async def test_probe_unreachable_server(Session, monkeypatch, exc_factory):
    tenant_id = await _seed_tenant(Session, configured=True)

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_factory(request)

    _mock_btcpay_http(monkeypatch, handler)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
    result = await btcpay_connection_test(current_user=None, tenant=tenant)

    assert result.model_dump(exclude={"detail"}) == {
        "url_reachable": False,
        "auth_ok": None,
        "store_found": None,
        "ok": False,
    }


async def test_probe_is_a_single_readonly_get(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session, configured=True)
    seen: list[httpx.Request] = []
    _mock_btcpay_http(monkeypatch, _status_handler(200, seen))

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
    await btcpay_connection_test(current_user=None, tenant=tenant)

    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == f"{SERVER_URL}/api/v1/stores/{STORE_ID}"


async def test_probe_requires_configuration_first(Session):
    tenant_id = await _seed_tenant(Session, configured=False)
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)

    with pytest.raises(HTTPException) as exc:
        await btcpay_connection_test(current_user=None, tenant=tenant)

    assert exc.value.status_code == 422
    assert "server URL" in exc.value.detail
    assert "API key" in exc.value.detail
    assert "store ID" in exc.value.detail


def test_interpret_store_probe_unexpected_status_is_not_ok():
    result = interpret_store_probe(503)
    assert result.ok is False
    assert result.url_reachable is True
    assert result.auth_ok is None and result.store_found is None
    assert "503" in result.detail


# ── Authorize deep link ────────────────────────────────────────────────────


async def test_authorize_url_builds_minimal_permission_set(Session):
    tenant_id = await _seed_tenant(Session, configured=True)
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)

    result = await get_btcpay_authorize_url(current_user=None, tenant=tenant)

    split = urlsplit(result.authorize_url)
    assert result.authorize_url.startswith(f"{SERVER_URL}/api-keys/authorize?")
    query = parse_qs(split.query)
    assert query["applicationName"] == ["OpenSplit"]
    assert query["selectiveStores"] == ["true"]
    assert query["permissions"] == BTCPAY_MINIMAL_PERMISSIONS
    assert result.permissions == BTCPAY_MINIMAL_PERMISSIONS
    # Exactly the documented minimal set — no store-settings write, no server
    # scope, nothing beyond what services/btcpay_client.py calls.
    assert set(BTCPAY_MINIMAL_PERMISSIONS) == {
        "btcpay.store.cancreateinvoice",
        "btcpay.store.canviewinvoices",
        "btcpay.store.canmanagepullpayments",
        "btcpay.store.canviewstoresettings",
    }


async def test_authorize_url_requires_saved_server_url(Session):
    tenant_id = await _seed_tenant(Session, configured=False)
    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)

    with pytest.raises(HTTPException) as exc:
        await get_btcpay_authorize_url(current_user=None, tenant=tenant)
    assert exc.value.status_code == 422
