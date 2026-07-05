"""BTCPayClient.get_payout_processors (PR 4.5): read-only probe of the store's
configured payout processors, used to detect a missing Lightning payout
processor and guide the operator.

The method must NEVER raise: on 404, a permission error (403), a non-200, an
unreachable server, or malformed JSON it returns None ("can't tell"), and only
returns a list when BTCPay answers 200 with a JSON array. Empty list is a valid
"reachable, none configured" answer — distinct from None.

All HTTP traffic is through httpx.MockTransport; no network.
"""

from __future__ import annotations

import httpx
import pytest

import app.services.btcpay_client as btcpay_module
from app.services.btcpay_client import BTCPayClient

pytestmark = pytest.mark.asyncio

STORE_ID = "store-abc123"
SERVER_URL = "https://btcpay.local"


def _mock_btcpay_http(monkeypatch, handler):
    real_async_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_async_client(
            transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout")
        )

    monkeypatch.setattr(btcpay_module.httpx, "AsyncClient", factory)


def _client() -> BTCPayClient:
    return BTCPayClient(SERVER_URL, "k", STORE_ID)


async def _run(monkeypatch, handler):
    _mock_btcpay_http(monkeypatch, handler)
    client = _client()
    try:
        return await client.get_payout_processors()
    finally:
        await client.close()


async def test_returns_list_when_processors_present(monkeypatch):
    processors = [{"name": "Lightning", "payoutMethodId": "BTC-LightningNetwork"}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/stores/{STORE_ID}/payout-processors")
        return httpx.Response(200, json=processors)

    assert await _run(monkeypatch, handler) == processors


async def test_returns_empty_list_when_none_configured(monkeypatch):
    # 200 + [] is a real answer: reachable, no processors — not None.
    result = await _run(monkeypatch, lambda r: httpx.Response(200, json=[]))
    assert result == []


async def test_returns_none_on_404(monkeypatch):
    assert await _run(monkeypatch, lambda r: httpx.Response(404, json={})) is None


async def test_returns_none_on_permission_error(monkeypatch):
    assert await _run(monkeypatch, lambda r: httpx.Response(403, json={})) is None


async def test_returns_none_when_unreachable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    assert await _run(monkeypatch, handler) is None


async def test_returns_none_on_non_list_body(monkeypatch):
    # Unexpected shape (object instead of array) → can't tell.
    result = await _run(monkeypatch, lambda r: httpx.Response(200, json={"x": 1}))
    assert result is None
