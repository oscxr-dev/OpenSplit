"""Guided BTCPay webhook setup (PR 3): generated secret + live verification.

Covers:
  * POST /tenants/me/btcpay/webhook-secret generates a urlsafe secret, stores
    it, and returns it EXACTLY ONCE, together with the composed webhook URL
    (from ORCHESTRATOR_PUBLIC_BASE_URL) and the two events to select in BTCPay
  * regenerating overwrites the secret and resets last_webhook_at
  * redaction contract extension: no other tenant endpoint ever serializes the
    generated secret — only btcpay_webhook_secret_set / last_webhook_at appear
  * the btcpay webhook handler stamps last_webhook_at on ANY signature-valid
    event (even non-actionable types); missing secret (403) and bad signature
    (401) leave it NULL
  * enforce_production_safety rejects a local-only public_base_url

Runs against the dedicated ``orchestrator_test`` Postgres database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.routers.webhooks as webhooks_mod
import app.services.btcpay_client as btcpay_module
import app.services.split_engine as split_mod
from app.config import Settings, settings
from app.models import Base, Payment, SplitRule, SplitTarget, Tenant
from app.routers.tenants import (
    BTCPAY_WEBHOOK_EVENTS,
    generate_btcpay_webhook_secret,
    get_btcpay_authorize_url,
    get_my_tenant,
    update_my_tenant,
)
from app.routers.webhooks import btcpay_webhook
from app.schemas import TenantUpdate
from app.services.btcpay_client import BTCPayClient

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

RAW_KEY = "sk-live-verysecret-btcpay-key-9F3A"
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


async def _seed_tenant(
    Session,
    *,
    webhook_secret: str | None = None,
    last_webhook_at: datetime | None = None,
) -> uuid.UUID:
    tenant = Tenant(
        id=uuid.uuid4(),
        name=f"Acme-{uuid.uuid4().hex[:8]}",
        adapter_type="btcpay",
        btcpay_url=SERVER_URL,
        btcpay_api_key=RAW_KEY,
        btcpay_store_id=STORE_ID,
        btcpay_webhook_secret=webhook_secret,
        last_webhook_at=last_webhook_at,
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


# ── Secret generation ──────────────────────────────────────────────────────


async def test_generate_returns_urlsafe_secret_and_stores_it(Session):
    tenant_id = await _seed_tenant(Session)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await generate_btcpay_webhook_secret(
            current_user=None, tenant=tenant, session=s
        )

    # secrets.token_urlsafe(32) → 43 chars from the URL-safe base64 alphabet.
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", resp.secret)
    assert resp.events == ["InvoiceSettled", "InvoicePaymentSettled"]
    assert resp.events == BTCPAY_WEBHOOK_EVENTS
    assert resp.webhook_url == (
        f"{settings.public_base_url}/api/v1/webhooks/btcpay/{tenant_id}"
    )

    async with Session() as s:
        stored = await _get_tenant(s, tenant_id)
        assert stored.btcpay_webhook_secret == resp.secret
        assert stored.last_webhook_at is None


async def test_webhook_url_follows_public_base_url(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session)
    monkeypatch.setattr(settings, "public_base_url", "https://pay.example.com")

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await generate_btcpay_webhook_secret(
            current_user=None, tenant=tenant, session=s
        )

    assert resp.webhook_url == f"https://pay.example.com/api/v1/webhooks/btcpay/{tenant_id}"


async def test_regenerate_overwrites_secret_and_resets_verification(Session):
    verified_at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    tenant_id = await _seed_tenant(
        Session, webhook_secret="old-secret", last_webhook_at=verified_at
    )

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        resp = await generate_btcpay_webhook_secret(
            current_user=None, tenant=tenant, session=s
        )

    assert resp.secret != "old-secret"
    async with Session() as s:
        stored = await _get_tenant(s, tenant_id)
        assert stored.btcpay_webhook_secret == resp.secret
        assert stored.last_webhook_at is None  # verification reset


async def test_two_generations_produce_distinct_secrets(Session):
    tenant_id = await _seed_tenant(Session)
    secrets_seen = set()
    for _ in range(2):
        async with Session() as s:
            tenant = await _get_tenant(s, tenant_id)
            resp = await generate_btcpay_webhook_secret(
                current_user=None, tenant=tenant, session=s
            )
            secrets_seen.add(resp.secret)
    assert len(secrets_seen) == 2


# ── Redaction contract (extends PR 2) ──────────────────────────────────────


def _mock_btcpay_http(monkeypatch, code: int = 200):
    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"id": STORE_ID})

    def factory(**kwargs):
        return real_async_client(
            transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout")
        )

    monkeypatch.setattr(btcpay_module.httpx, "AsyncClient", factory)


async def test_generated_secret_never_serialized_by_other_endpoints(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session)
    _mock_btcpay_http(monkeypatch)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        generated = await generate_btcpay_webhook_secret(
            current_user=None, tenant=tenant, session=s
        )
        secret = generated.secret

        bodies: dict[str, str] = {}
        health = await get_my_tenant(current_user=None, tenant=tenant)
        bodies["GET /tenants/me"] = health.model_dump_json()
        patched = await update_my_tenant(
            TenantUpdate(name="Still Acme"), current_user=None, tenant=tenant, session=s
        )
        bodies["PATCH /tenants/me"] = patched.model_dump_json()
        authorize = await get_btcpay_authorize_url(current_user=None, tenant=tenant)
        bodies["GET /tenants/me/btcpay/authorize-url"] = authorize.model_dump_json()

    for endpoint, body in bodies.items():
        assert secret not in body, endpoint
        assert '"btcpay_webhook_secret":' not in body, endpoint

    # The only readable traces: the presence flag and the verification stamp.
    assert health.tenant.btcpay_webhook_secret_set is True
    assert health.tenant.last_webhook_at is None
    assert '"btcpay_webhook_secret_set":true' in bodies["GET /tenants/me"]
    assert '"last_webhook_at":' in bodies["GET /tenants/me"]
    assert patched.btcpay_webhook_secret_set is True


async def test_secret_unset_reports_false_flag(Session, monkeypatch):
    tenant_id = await _seed_tenant(Session)
    _mock_btcpay_http(monkeypatch)

    async with Session() as s:
        tenant = await _get_tenant(s, tenant_id)
        health = await get_my_tenant(current_user=None, tenant=tenant)

    assert health.tenant.btcpay_webhook_secret_set is False
    assert health.tenant.last_webhook_at is None


# ── Webhook handler: last_webhook_at stamping ──────────────────────────────


class FakeRequest:
    def __init__(self, body: bytes, sig: str | None = None) -> None:
        self._body = body
        self.headers: dict[str, str] = {}
        if sig is not None:
            self.headers["BTCPay-Sig"] = sig

    async def body(self) -> bytes:
        return self._body


class FakeBTCPay:
    """Fake payout client with REAL HMAC verification (delegated to the
    production implementation) so signature behaviour is exercised for real."""

    def __init__(self, base_url=None, api_key=None, store_id=None):
        pass

    async def get_invoice(self, invoice):
        return {"amount": "10000", "currency": "SATS"}

    async def get_invoice_payment_methods(self, invoice):
        return []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        return {"id": "payout-1"}

    async def close(self):
        pass

    verify_webhook_sig = staticmethod(BTCPayClient.verify_webhook_sig)


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    monkeypatch.setattr(webhooks_mod, "BTCPayClient", FakeBTCPay)
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)


SECRET = "test-webhook-secret"


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _event_body(event_type: str, invoice_id: str = "inv-1") -> bytes:
    return json.dumps(
        {"type": event_type, "invoiceId": invoice_id, "metadata": {}}
    ).encode()


async def _seed_webhook_tenant(Session, *, webhook_secret: str | None) -> uuid.UUID:
    """BTCPay tenant + active 100% rule + one pending payment for inv-1."""
    tenant_id = await _seed_tenant(Session, webhook_secret=webhook_secret)
    async with Session() as s:
        rule = SplitRule(tenant_id=tenant_id, name="Default", active=True, version=1)
        s.add(rule)
        await s.flush()
        s.add(
            SplitTarget(
                split_rule_id=rule.id,
                label="Alice",
                ln_address="alice@example.com",
                percentage=100,
                order=0,
            )
        )
        s.add(
            Payment(
                tenant_id=tenant_id,
                invoice_id="inv-1",
                bolt11="lnbc-test",
                amount_sats=10_000,
                status="pending",
                split_rule_id=rule.id,
            )
        )
        await s.commit()
    return tenant_id


async def _last_webhook_at(Session, tenant_id: uuid.UUID) -> datetime | None:
    async with Session() as s:
        return (await _get_tenant(s, tenant_id)).last_webhook_at


async def test_signature_valid_ignored_event_still_stamps_last_webhook_at(Session):
    """ANY signature-valid delivery proves liveness — even event types the
    handler does not act on."""
    tenant_id = await _seed_webhook_tenant(Session, webhook_secret=SECRET)

    body = _event_body("InvoiceCreated")
    async with Session() as s:
        result = await btcpay_webhook(
            tenant_id=tenant_id,
            request=FakeRequest(body, sig=_sign(body, SECRET)),
            session=s,
        )

    assert result["status"] == "ignored"
    stamped = await _last_webhook_at(Session, tenant_id)
    assert stamped is not None


async def test_signature_valid_settled_event_stamps_last_webhook_at(Session):
    tenant_id = await _seed_webhook_tenant(Session, webhook_secret=SECRET)

    body = _event_body("InvoiceSettled")
    async with Session() as s:
        result = await btcpay_webhook(
            tenant_id=tenant_id,
            request=FakeRequest(body, sig=_sign(body, SECRET)),
            session=s,
        )

    assert result["status"] == "ok"
    assert await _last_webhook_at(Session, tenant_id) is not None


async def test_invalid_signature_does_not_stamp_last_webhook_at(Session):
    tenant_id = await _seed_webhook_tenant(Session, webhook_secret=SECRET)

    body = _event_body("InvoiceSettled")
    for bad_sig in (None, _sign(body, "wrong-secret")):
        with pytest.raises(HTTPException) as exc:
            async with Session() as s:
                await btcpay_webhook(
                    tenant_id=tenant_id,
                    request=FakeRequest(body, sig=bad_sig),
                    session=s,
                )
        assert exc.value.status_code == 401

    assert await _last_webhook_at(Session, tenant_id) is None


async def test_missing_secret_does_not_stamp_last_webhook_at(Session):
    tenant_id = await _seed_webhook_tenant(Session, webhook_secret=None)

    body = _event_body("InvoiceSettled")
    with pytest.raises(HTTPException) as exc:
        async with Session() as s:
            await btcpay_webhook(
                tenant_id=tenant_id,
                request=FakeRequest(body, sig=_sign(body, "whatever")),
                session=s,
            )

    assert exc.value.status_code == 403
    assert await _last_webhook_at(Session, tenant_id) is None


# ── Production safety ──────────────────────────────────────────────────────


def _secure_production_settings(**overrides) -> Settings:
    kwargs = dict(
        environment="production",
        jwt_secret="p" * 64,
        lnbits_webhook_secret="q" * 32,
        seed_admin_password="r" * 32,
        cors_origins=["https://dash.example.com"],
    )
    kwargs.update(overrides)
    return Settings(**kwargs)


@pytest.fixture
def _no_public_base_url_env(monkeypatch):
    # The container may export ORCHESTRATOR_PUBLIC_BASE_URL; drop it so these
    # tests exercise the code default.
    monkeypatch.delenv("ORCHESTRATOR_PUBLIC_BASE_URL", raising=False)


@pytest.mark.parametrize(
    "base_url",
    [
        None,  # code default http://localhost:8000
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://host.docker.internal:8000",
    ],
)
async def test_production_rejects_local_only_public_base_url(_no_public_base_url_env, base_url):
    overrides = {} if base_url is None else {"public_base_url": base_url}
    cfg = _secure_production_settings(**overrides)
    with pytest.raises(RuntimeError, match="ORCHESTRATOR_PUBLIC_BASE_URL"):
        cfg.enforce_production_safety()


async def test_production_accepts_public_base_url(_no_public_base_url_env):
    cfg = _secure_production_settings(public_base_url="https://opensplit.example.com/")
    # Trailing slash is normalized away and the config passes the safety gate.
    assert cfg.public_base_url == "https://opensplit.example.com"
    cfg.enforce_production_safety()  # must not raise


async def test_development_keeps_working_with_the_localhost_default(_no_public_base_url_env):
    cfg = Settings(environment="development")
    assert cfg.public_base_url == "http://localhost:8000"
    cfg.enforce_production_safety()  # no-op outside production
