"""Payout durability: per-target commits and idempotent resume after a crash.

The split-execution loop must persist each split's btcpay_payout_id as it is
created, not in one end-of-loop commit, so a crash mid-loop leaves an accurate
audit trail and a reprocess never double-pays.

Runs against Postgres on the dedicated orchestrator_test database; no real
Lightning/BTCPay calls are made. The crash is simulated with a BaseException
subclass, which — like a process kill or task cancellation — the engine's
per-target `except Exception` cannot swallow.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.split_engine as split_mod
from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.services.split_engine import SplitEngine

pytestmark = pytest.mark.asyncio

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"

AMOUNT_SATS = 10_000
LABELS = ["Alice", "Bob", "Carol", "Dave"]  # 25% each → 2_500 sats per target


class SimulatedCrash(BaseException):
    """Stands in for a process crash mid-loop; not caught by `except Exception`."""


class CrashingBTCPay:
    """Returns payout ids for the first ``crash_after`` calls, then "the
    process dies" at the start of the next call (that payout is NOT created)."""

    def __init__(self, crash_after: int) -> None:
        self.crash_after = crash_after
        self.calls: list[tuple[str, int]] = []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        if len(self.calls) >= self.crash_after:
            raise SimulatedCrash()
        self.calls.append((ln_address, amount_sats))
        return {"id": f"payout-crash-{len(self.calls)}"}

    async def close(self):
        pass


class OkBTCPay:
    def __init__(self, prefix: str = "payout-resume") -> None:
        self.prefix = prefix
        self.calls: list[tuple[str, int]] = []

    async def payout_to_ln_address(self, amount_sats, ln_address, label=""):
        self.calls.append((ln_address, amount_sats))
        return {"id": f"{self.prefix}-{len(self.calls)}"}

    async def close(self):
        pass


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


async def _seed(Session) -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]:
    """Tenant + one active rule with four 25% targets + one pending payment."""
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Durability-{tenant_id.hex[:8]}",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.test",
            btcpay_api_key="test-key",
            btcpay_store_id="store-1",
            btcpay_webhook_secret="test-webhook-secret",
            active=True,
        )
        rule = SplitRule(tenant_id=tenant_id, name="Durability", active=True, version=1)
        s.add_all([tenant, rule])
        await s.flush()
        targets = [
            SplitTarget(
                split_rule_id=rule.id,
                label=label,
                ln_address=f"{label.lower()}@example.com",
                percentage=25,
                order=i,
            )
            for i, label in enumerate(LABELS)
        ]
        s.add_all(targets)
        await s.flush()
        target_ids = [t.id for t in targets]

        payment_id = uuid.uuid4()
        s.add(
            Payment(
                id=payment_id,
                tenant_id=tenant_id,
                invoice_id=f"inv-{payment_id.hex[:8]}",
                bolt11="lnbc-test",
                amount_sats=AMOUNT_SATS,
                status="pending",
            )
        )
        await s.commit()
    return tenant_id, target_ids, payment_id


async def _crash_mid_loop(Session, payment_id, crash_after: int) -> CrashingBTCPay:
    """Run the loop until the mock 'kills the process' after ``crash_after``
    payouts; the crashed session is closed without further commits."""
    crash = CrashingBTCPay(crash_after=crash_after)
    session = Session()
    try:
        with pytest.raises(SimulatedCrash):
            await SplitEngine(session, lnbits_client=None).execute_splits_btcpay(
                payment_id, crash
            )
    finally:
        await session.close()
    return crash


async def _db_state(Session, payment_id):
    async with Session() as s:
        payment = (
            await s.execute(select(Payment).where(Payment.id == payment_id))
        ).scalar_one()
        rows = list(
            (
                await s.execute(
                    select(PaymentSplit).where(PaymentSplit.payment_id == payment_id)
                )
            ).scalars()
        )
    return payment, {r.split_target_id: r for r in rows}


async def test_crash_mid_loop_persists_each_created_payout_id(Session, monkeypatch):
    """Crash after 2 of 4 payouts: both created ids are durably committed,
    the interrupted target has a committed pre-flight row without an id,
    the unreached target has no row, and the payment stays recoverable."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    _, target_ids, payment_id = await _seed(Session)

    await _crash_mid_loop(Session, payment_id, crash_after=2)

    payment, by_target = await _db_state(Session, payment_id)

    assert by_target[target_ids[0]].btcpay_payout_id == "payout-crash-1"
    assert by_target[target_ids[1]].btcpay_payout_id == "payout-crash-2"
    assert by_target[target_ids[0]].status == "in_progress"
    assert by_target[target_ids[1]].status == "in_progress"
    assert by_target[target_ids[0]].amount_sats == 2_500
    assert by_target[target_ids[1]].amount_sats == 2_500

    # Interrupted target: durable pre-flight marker, payout never created.
    assert by_target[target_ids[2]].status == "pending"
    assert by_target[target_ids[2]].btcpay_payout_id is None

    # Never-reached target: no row at all (provably no payout attempted).
    assert target_ids[3] not in by_target
    assert len(by_target) == 3

    assert payment.status == "in_progress"


async def test_resume_creates_only_missing_payouts_never_double_pays(
    Session, monkeypatch
):
    """Reprocess after the crash finishes only the unpaid targets: total
    payouts created across both runs == number of targets, never more, and a
    further resume creates nothing."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    _, target_ids, payment_id = await _seed(Session)

    crash = await _crash_mid_loop(Session, payment_id, crash_after=2)

    ok = OkBTCPay()
    async with Session() as s:
        records = await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(
            payment_id, ok, resume=True
        )

    # Only the interrupted + missing targets were paid: 2 + 2 == 4 targets.
    assert len(ok.calls) == 2
    assert len(crash.calls) + len(ok.calls) == len(target_ids)
    assert len(records) == len(target_ids)

    payment, by_target = await _db_state(Session, payment_id)
    assert len(by_target) == 4
    # Already-created payouts kept their original ids (not re-sent).
    assert by_target[target_ids[0]].btcpay_payout_id == "payout-crash-1"
    assert by_target[target_ids[1]].btcpay_payout_id == "payout-crash-2"
    assert by_target[target_ids[0]].retry_count == 0
    # The interrupted pre-flight row was retried in place.
    assert by_target[target_ids[2]].btcpay_payout_id == "payout-resume-1"
    assert by_target[target_ids[2]].retry_count == 1
    # The unreached target got a fresh row + payout.
    assert by_target[target_ids[3]].btcpay_payout_id == "payout-resume-2"
    assert by_target[target_ids[3]].retry_count == 0
    # Split math unchanged: every target got exactly its 25% share.
    assert [by_target[t].amount_sats for t in target_ids] == [2_500] * 4
    assert all(r.status == "in_progress" for r in by_target.values())
    assert payment.status == "in_progress"

    # A second resume is a no-op: every target already has a payout recorded.
    dup = OkBTCPay(prefix="payout-dup")
    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(
            payment_id, dup, resume=True
        )
    assert dup.calls == []
    _, by_target_after = await _db_state(Session, payment_id)
    assert {
        t: r.btcpay_payout_id for t, r in by_target_after.items()
    } == {t: r.btcpay_payout_id for t, r in by_target.items()}


async def test_plain_rerun_after_crash_pays_nothing(Session, monkeypatch):
    """Without an explicit resume (e.g. a redelivered webhook), a crashed
    in_progress payment is left untouched — no payout is ever sent."""
    monkeypatch.setattr(split_mod, "load_lnd_receiver", lambda label: None)
    _, target_ids, payment_id = await _seed(Session)

    await _crash_mid_loop(Session, payment_id, crash_after=2)

    plain = OkBTCPay(prefix="payout-plain")
    async with Session() as s:
        await SplitEngine(s, lnbits_client=None).execute_splits_btcpay(
            payment_id, plain
        )

    assert plain.calls == []
    payment, by_target = await _db_state(Session, payment_id)
    assert len(by_target) == 3  # unchanged from the crash state
    assert payment.status == "in_progress"
