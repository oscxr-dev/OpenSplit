"""Tests for dynamic LND receivers (fresh-invoice demo payouts).

Covers env-based config loading, cert hex decoding, LND invoice minting and the
BTCPay BOLT11 payout call. Network calls are stubbed with httpx.MockTransport,
so no real LND node or BTCPay server is required.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.btcpay_client import BTCPayClient
from app.services.lnd_client import (
    LNDClient,
    LNDReceiverConfig,
    cert_hex_to_pem,
    load_lnd_receiver,
)

SAMPLE_PEM = (
    "-----BEGIN CERTIFICATE-----\nMIIBfakecertdata==\n-----END CERTIFICATE-----\n"
)
SAMPLE_CERT_HEX = SAMPLE_PEM.encode("ascii").hex()


# ── Config loading ────────────────────────────────────────────────────
def test_load_returns_none_when_unset():
    assert load_lnd_receiver("Carol", env={}) is None


def test_load_returns_none_on_partial_config():
    env = {
        "LND_RECEIVER_CAROL_URL": "https://127.0.0.1:8080",
        "LND_RECEIVER_CAROL_MACAROON_HEX": "abcd",
        # TLS cert missing → not configured
    }
    assert load_lnd_receiver("Carol", env=env) is None


def test_load_returns_config_when_complete():
    env = {
        "LND_RECEIVER_CAROL_URL": "https://127.0.0.1:8080/",
        "LND_RECEIVER_CAROL_MACAROON_HEX": "0a0b0c",
        "LND_RECEIVER_CAROL_TLS_CERT_HEX": SAMPLE_CERT_HEX,
    }
    cfg = load_lnd_receiver("Carol", env=env)
    assert cfg is not None
    assert cfg.label == "Carol"
    assert cfg.rest_url == "https://127.0.0.1:8080"  # trailing slash trimmed
    assert cfg.macaroon_hex == "0a0b0c"
    assert cfg.tls_cert_hex == SAMPLE_CERT_HEX


def test_label_slug_normalisation():
    env = {
        "LND_RECEIVER_DAVE_DOE_URL": "https://node",
        "LND_RECEIVER_DAVE_DOE_MACAROON_HEX": "ff",
        "LND_RECEIVER_DAVE_DOE_TLS_CERT_HEX": SAMPLE_CERT_HEX,
    }
    # "Dave Doe" → DAVE_DOE
    assert load_lnd_receiver("Dave Doe", env=env) is not None
    # A label with no matching vars stays unconfigured.
    assert load_lnd_receiver("Barista", env=env) is None


def test_cert_hex_round_trip():
    assert cert_hex_to_pem(SAMPLE_CERT_HEX) == SAMPLE_PEM


# ── LND invoice minting ───────────────────────────────────────────────
def _cfg() -> LNDReceiverConfig:
    return LNDReceiverConfig(
        label="Carol",
        rest_url="https://lnd.local:8080",
        macaroon_hex="deadbeef",
        tls_cert_hex=SAMPLE_CERT_HEX,
    )


@pytest.mark.asyncio
async def test_create_invoice_posts_amount_and_macaroon():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["macaroon"] = request.headers.get("Grpc-Metadata-macaroon")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"payment_request": "lnbc1500n1xyz"})

    lnd = LNDClient(_cfg())
    lnd._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        bolt11 = await lnd.create_invoice(amount_sats=1500, memo="Demo → Carol")
    finally:
        await lnd.close()

    assert bolt11 == "lnbc1500n1xyz"
    assert seen["url"] == "https://lnd.local:8080/v1/invoices"
    assert seen["macaroon"] == "deadbeef"
    assert seen["body"]["value"] == "1500"  # int64 serialised as string
    assert seen["body"]["memo"] == "Demo → Carol"


@pytest.mark.asyncio
async def test_create_invoice_rejects_non_positive_amount():
    lnd = LNDClient(_cfg())
    with pytest.raises(ValueError):
        await lnd.create_invoice(amount_sats=0)


@pytest.mark.asyncio
async def test_create_invoice_raises_without_payment_request():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"r_hash": "abc"})

    lnd = LNDClient(_cfg())
    lnd._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError):
            await lnd.create_invoice(amount_sats=1000)
    finally:
        await lnd.close()


# ── BTCPay BOLT11 payout ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_payout_to_bolt11_sends_invoice_as_destination():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "payout-123", "state": "AwaitingPayment"})

    btcpay = BTCPayClient(base_url="https://btcpay.local", api_key="k", store_id="store1")
    btcpay._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        payout = await btcpay.payout_to_bolt11("lnbc1500n1xyz", label="Demo → Carol")
    finally:
        await btcpay.close()

    assert payout["id"] == "payout-123"
    assert seen["url"] == "https://btcpay.local/api/v1/stores/store1/payouts"
    assert seen["body"]["destination"] == "lnbc1500n1xyz"
    assert seen["body"]["payoutMethodId"] == "BTC-LightningNetwork"
    assert seen["body"]["approved"] is True
    # Amount is carried by the invoice — none is sent explicitly.
    assert "amount" not in seen["body"]
