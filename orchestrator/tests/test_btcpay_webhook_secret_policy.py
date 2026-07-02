"""Strict BTCPay webhook secret policy.

A tenant without a configured webhook secret must not process BTCPay webhooks
at all (403 before the body is even parsed) — unsigned events would be
trivially forgeable. With a secret configured, an invalid signature is rejected
(401) and a correctly signed webhook is processed as before.

Runs against the dedicated ``orchestrator_test`` Postgres database; no real
Lightning/BTCPay calls are made.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.routers.webhooks as webhooks_mod
import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, SplitRule, SplitTarget, Tenant
from app.routers.webhooks import btcpay_webhook
from app.services.btcpay_client import BTCPayClient

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

SECRET = "test-webhook-secret"


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

    payout_calls: list[tuple[str, int]] = []

    def __init__(self, base_url=None, api_key=None, store_id=None):
        pass

    async def get_invoice(self, invoice):
        return {"amount": "10000", "currency": "SATS"}

    async def get_invoice_payment_methods(self, invoice):
        return []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        FakeBTCPay.payout_calls.append((ln_address, amount_sats))
        return {"id": f"payout-{len(FakeBTCPay.payout_calls)}"}

    async def close(self):
        pass

    verify_webhook_sig = staticmethod(BTCPayClient.verify_webhook_sig)


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _settled_body(invoice_id: str) -> bytes:
    return json.dumps(
        {"type": "InvoiceSettled", "invoiceId": invoice_id, "metadata": {}}
    ).encode()


async def _seed(Session, *, webhook_secret: str | None, invoice_id: str) -> uuid.UUID:
    """BTCPay tenant + active 100% rule + one pending payment for invoice_id."""
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Acme-{tenant_id.hex[:8]}",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.test",
            btcpay_api_key="test-key",
            btcpay_store_id="store-1",
            btcpay_webhook_secret=webhook_secret,
            active=True,
        )
        rule = SplitRule(tenant_id=tenant_id, name="Default", active=True, version=1)
        s.add_all([tenant, rule])
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
                invoice_id=invoice_id,
                bolt11="lnbc-test",
                amount_sats=10_000,
                status="pending",
                split_rule_id=rule.id,
            )
        )
        await s.commit()
    return tenant_id


async def _payment_status(Session, invoice_id: str) -> str:
    async with Session() as s:
        return (
            await s.execute(
                select(Payment.status).where(Payment.invoice_id == invoice_id)
            )
        ).scalar_one()


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    FakeBTCPay.payout_calls = []
    monkeypatch.setattr(webhooks_mod, "BTCPayClient", FakeBTCPay)
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)


async def test_missing_webhook_secret_rejects_webhook(Session):
    invoice_id = "inv-no-secret"
    tenant_id = await _seed(Session, webhook_secret=None, invoice_id=invoice_id)

    body = _settled_body(invoice_id)
    # Even a "signed" request is refused: with no secret there is nothing to
    # verify against, so nothing may be processed.
    with pytest.raises(HTTPException) as exc:
        async with Session() as s:
            await btcpay_webhook(
                tenant_id=tenant_id,
                request=FakeRequest(body, sig=_sign(body, "whatever")),
                session=s,
            )

    assert exc.value.status_code == 403
    assert FakeBTCPay.payout_calls == []
    assert await _payment_status(Session, invoice_id) == "pending"


async def test_empty_webhook_secret_rejects_webhook(Session):
    invoice_id = "inv-empty-secret"
    tenant_id = await _seed(Session, webhook_secret="", invoice_id=invoice_id)

    with pytest.raises(HTTPException) as exc:
        async with Session() as s:
            await btcpay_webhook(
                tenant_id=tenant_id,
                request=FakeRequest(_settled_body(invoice_id)),
                session=s,
            )

    assert exc.value.status_code == 403
    assert FakeBTCPay.payout_calls == []
    assert await _payment_status(Session, invoice_id) == "pending"


async def test_invalid_signature_rejects_webhook(Session):
    invoice_id = "inv-bad-sig"
    tenant_id = await _seed(Session, webhook_secret=SECRET, invoice_id=invoice_id)

    body = _settled_body(invoice_id)
    for bad_sig in (None, _sign(body, "wrong-secret")):
        with pytest.raises(HTTPException) as exc:
            async with Session() as s:
                await btcpay_webhook(
                    tenant_id=tenant_id,
                    request=FakeRequest(body, sig=bad_sig),
                    session=s,
                )
        assert exc.value.status_code == 401

    assert FakeBTCPay.payout_calls == []
    assert await _payment_status(Session, invoice_id) == "pending"


async def test_valid_signature_with_secret_processes_webhook(Session):
    invoice_id = "inv-good-sig"
    tenant_id = await _seed(Session, webhook_secret=SECRET, invoice_id=invoice_id)

    body = _settled_body(invoice_id)
    async with Session() as s:
        result = await btcpay_webhook(
            tenant_id=tenant_id,
            request=FakeRequest(body, sig=_sign(body, SECRET)),
            session=s,
        )

    assert result["status"] == "ok"
    assert FakeBTCPay.payout_calls == [("alice@example.com", 10_000)]
