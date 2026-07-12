"""Relay publishing through the proof endpoints (sign + /proof/publish).

Same harness as test_nostr_sign_endpoint (Postgres orchestrator_test DB,
router coroutines called directly) with the websocket seam faked at the
service level, so the real publish code runs end to end without a network.

The contract under test: publishing is best-effort — relays down or slow can
never fail signing, never touch money state, and every attempt leaves honest
per-relay results in payments.nostr_relay_results.
"""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.models import Payment, PaymentSplit
from app.routers.proof import get_split_proof, publish_split_proof, sign_split_proof
from app.services import nostr_publish

from test_nostr_publish import FakeRelay
from test_nostr_sign_endpoint import (  # noqa: F401  (engine is used via Session)
    SECKEY_HEX,
    Session,
    _seed,
    _sign,
    _stored_payment,
    engine,
)

pytestmark = pytest.mark.asyncio

GOOD = "wss://good.test"
DOWN = "wss://down.test"


class AckRelay(FakeRelay):
    """Acks whichever event it just received — endpoint tests sign REAL
    events whose ids are not known up front, so a canned OK frame would
    never match and the publish would time out instead."""

    async def recv(self) -> str:
        if not self.sent:
            await asyncio.Event().wait()  # protocol violation: ack before EVENT
        event = json.loads(self.sent[0])[1]
        return json.dumps(["OK", event["id"], True, ""])


@pytest_asyncio.fixture
async def signing_env(monkeypatch):
    monkeypatch.setattr(settings, "nostr_seckey", SECKEY_HEX)


def wire(monkeypatch, *, relays: list[str], factories: dict) -> list[str]:
    """Configure settings.nostr_relays and fake the websocket seam.

    ``factories`` maps relay URL -> zero-arg FakeRelay factory (a fresh fake
    per connection, since publish may run more than once per test). Returns
    a list recording every connect attempt.
    """
    attempts: list[str] = []

    def connect(url, **kwargs):
        attempts.append(url)
        return factories[url]()

    monkeypatch.setattr(settings, "nostr_relays", relays)
    monkeypatch.setattr(nostr_publish, "ws_connect", connect)
    return attempts


async def _publish(Session, tenant, payment_id):
    async with Session() as s:
        return await publish_split_proof(
            payment_id, current_user=None, tenant=tenant, session=s
        )


# ── Signing publishes best-effort ──────────────────────────────────────────
async def test_sign_publishes_and_persists_per_relay_results(
    Session, signing_env, monkeypatch
):
    wire(
        monkeypatch,
        relays=[GOOD, DOWN],
        factories={
            GOOD: lambda: AckRelay(),
            DOWN: lambda: FakeRelay(connect_error=OSError("refused")),
        },
    )
    tenant, payment_id = await _seed(Session)

    result = await _sign(Session, tenant, payment_id)

    # The response carries both outcomes, honestly.
    by_relay = {r.relay: r for r in result.relay_results}
    assert by_relay[GOOD].ok is True and by_relay[GOOD].error is None
    assert by_relay[DOWN].ok is False and "refused" in by_relay[DOWN].error

    # And they are persisted alongside the (unaffected) signed event.
    payment = await _stored_payment(Session, payment_id)
    stored = json.loads(payment.nostr_relay_results)
    assert {(r["relay"], r["ok"]) for r in stored} == {(GOOD, True), (DOWN, False)}
    assert payment.nostr_proof_event == result.event_json


async def test_sign_succeeds_even_when_every_relay_fails(
    Session, signing_env, monkeypatch
):
    wire(
        monkeypatch,
        relays=[GOOD, DOWN],
        factories={
            GOOD: lambda: FakeRelay(connect_error=OSError("refused")),
            DOWN: lambda: FakeRelay(connect_error=OSError("refused")),
        },
    )
    tenant, payment_id = await _seed(Session)

    result = await _sign(Session, tenant, payment_id)

    assert result.event_id  # signing itself succeeded
    assert all(r.ok is False for r in result.relay_results)
    payment = await _stored_payment(Session, payment_id)
    assert payment.nostr_proof_event == result.event_json


async def test_sign_with_no_relays_configured_skips_publishing_silently(
    Session, signing_env, monkeypatch
):
    # conftest already forces nostr_relays=[]; also prove no connect happens.
    def never(url, **kwargs):
        raise AssertionError("must not connect with no relays configured")

    monkeypatch.setattr(nostr_publish, "ws_connect", never)
    tenant, payment_id = await _seed(Session)

    result = await _sign(Session, tenant, payment_id)

    assert result.relay_results is None
    assert (await _stored_payment(Session, payment_id)).nostr_relay_results is None


# ── The re-publish endpoint ────────────────────────────────────────────────
async def test_publish_requires_a_signed_proof(Session, signing_env, monkeypatch):
    monkeypatch.setattr(settings, "nostr_relays", [GOOD])
    tenant, payment_id = await _seed(Session)

    with pytest.raises(HTTPException) as exc:
        await _publish(Session, tenant, payment_id)
    assert exc.value.status_code == 409
    assert "sign" in exc.value.detail.lower()


async def test_publish_with_no_relays_configured_is_422(Session, signing_env):
    tenant, payment_id = await _seed(Session)
    await _sign(Session, tenant, payment_id)  # relays [] → signed, unpublished

    with pytest.raises(HTTPException) as exc:
        await _publish(Session, tenant, payment_id)
    assert exc.value.status_code == 422
    assert "ORCHESTRATOR_NOSTR_RELAYS" in exc.value.detail


async def test_publish_other_tenants_payment_is_invisible(
    Session, signing_env, monkeypatch
):
    monkeypatch.setattr(settings, "nostr_relays", [GOOD])
    tenant, payment_id = await _seed(Session)
    await _sign(Session, tenant, payment_id)
    other, _ = await _seed(Session)

    with pytest.raises(HTTPException) as exc:
        await _publish(Session, other, payment_id)
    assert exc.value.status_code == 404


async def test_republish_is_idempotent_and_refreshes_results(
    Session, signing_env, monkeypatch
):
    # First: sign while the relay is down → failure recorded.
    state = {"up": False}

    def relay_factory():
        if state["up"]:
            return AckRelay()
        return FakeRelay(connect_error=OSError("refused"))

    wire(monkeypatch, relays=[GOOD], factories={GOOD: relay_factory})
    tenant, payment_id = await _seed(Session)
    signed = await _sign(Session, tenant, payment_id)
    assert signed.relay_results[0].ok is False

    # Later: relay recovers → re-publish flips the recorded outcome.
    state["up"] = True
    republished = await _publish(Session, tenant, payment_id)

    assert republished.relay_results[0].ok is True
    # Idempotent: the immutable signed event is byte-identical, same id, and
    # the single results column just refreshed — no new rows anywhere.
    assert republished.event_json == signed.event_json
    assert republished.event_id == signed.event_id
    payment = await _stored_payment(Session, payment_id)
    assert payment.nostr_proof_event == signed.event_json
    assert json.loads(payment.nostr_relay_results)[0]["ok"] is True
    async with Session() as s:
        count = len(
            (await s.execute(select(Payment.id).where(Payment.id == payment_id)))
            .scalars()
            .all()
        )
    assert count == 1

    # And GET /proof shows the refreshed results.
    async with Session() as s:
        proof = await get_split_proof(
            payment_id, current_user=None, tenant=tenant, session=s
        )
    assert proof.nostr_proof.relay_results[0].ok is True


async def test_resign_drops_stale_relay_results(Session, signing_env, monkeypatch):
    wire(monkeypatch, relays=[GOOD], factories={GOOD: lambda: AckRelay()})
    tenant, payment_id = await _seed(Session)
    first = await _sign(Session, tenant, payment_id)
    assert first.relay_results[0].ok is True

    # State changes (preimage backfill) force a fresh event on re-sign; with
    # publishing now disabled, the old event's results must not linger.
    async with Session() as s:
        split = (
            await s.execute(
                select(PaymentSplit).where(
                    PaymentSplit.payment_id == payment_id,
                    PaymentSplit.amount_sats == 7000,
                )
            )
        ).scalar_one()
        split.ln_preimage = "dd" * 32
        split.ln_payment_hash = "ee" * 32
        await s.commit()
    monkeypatch.setattr(settings, "nostr_relays", [])

    second = await _sign(Session, tenant, payment_id)

    assert second.event_id != first.event_id
    assert second.relay_results is None
    assert (await _stored_payment(Session, payment_id)).nostr_relay_results is None


async def test_publish_leaves_money_state_untouched(
    Session, signing_env, monkeypatch
):
    wire(monkeypatch, relays=[GOOD], factories={GOOD: lambda: AckRelay()})
    tenant, payment_id = await _seed(Session)
    await _sign(Session, tenant, payment_id)

    async def snapshot():
        async with Session() as s:
            payment = (
                await s.execute(select(Payment).where(Payment.id == payment_id))
            ).scalar_one()
            splits = (
                (
                    await s.execute(
                        select(PaymentSplit)
                        .where(PaymentSplit.payment_id == payment_id)
                        .order_by(PaymentSplit.amount_sats)
                    )
                )
                .scalars()
                .all()
            )
        return (
            payment.status,
            payment.amount_sats,
            payment.paid_at,
            payment.unallocated_store_sats,
            payment.pending_remainder_sats,
            payment.nostr_proof_event,
            [(sp.status, sp.amount_sats, sp.btcpay_payout_id) for sp in splits],
        )

    before = await snapshot()
    await _publish(Session, tenant, payment_id)
    assert await snapshot() == before
