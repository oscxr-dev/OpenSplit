from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.services.payout_reconciliation as reconciliation_mod
from app.config import settings
from app.models import Base, Payment, PaymentSplit, SplitRule, SplitTarget, Tenant
from app.services.payout_reconciliation import (
    extract_ln_settlement,
    map_btcpay_payout_state,
    payout_failure_reason,
    reconcile_tenant_payouts,
)

# A real Lightning settlement proof captured from a regtest BTCPay payout
# (GET /api/v1/stores/{store}/payouts/{id}). Note the PascalCase keys — BTCPay
# returns the stored proof blob verbatim, unlike the camelCased payout fields.
REAL_PREIMAGE = "c6aa922406355f1f201daea3e46d451576657016026dfe4872bf47835e08b75e"
REAL_PAYMENT_HASH = "77850d754d7177072f799a77cf6886f79adc029ecc02a52d781b3959af430ffe"
REAL_PAYMENT_PROOF = {
    "Id": REAL_PAYMENT_HASH,
    "Link": None,
    "Preimage": REAL_PREIMAGE,
    "ProofType": "PayoutLightningBlob",
    "PaymentHash": REAL_PAYMENT_HASH,
}

_BASE_URL = settings.db_url.rsplit("/", 1)[0]
TEST_DB_URL = f"{_BASE_URL}/orchestrator_test"


def test_btcpay_payout_state_mapping():
    assert map_btcpay_payout_state("AwaitingApproval") == "in_progress"
    assert map_btcpay_payout_state("AwaitingPayment") == "in_progress"
    assert map_btcpay_payout_state("InProgress") == "in_progress"
    assert map_btcpay_payout_state("Completed") == "completed"
    assert map_btcpay_payout_state("Cancelled") == "failed"


def test_unknown_btcpay_state_stays_non_terminal():
    assert map_btcpay_payout_state("UnexpectedFutureState") == "in_progress"


def test_failure_reason_handles_different_btcpay_shapes():
    assert payout_failure_reason(
        {"paymentProof": {"error": "No route found"}}, "Cancelled"
    ) == "No route found"
    assert payout_failure_reason(
        {"paymentProof": "opaque-proof"}, "Cancelled"
    ) == "BTCPay reportó el payout como Cancelled."


# ── Lightning settlement proof extraction (pure) ────────────────────────────


def test_extract_ln_settlement_from_real_pascalcase_shape():
    preimage, payment_hash = extract_ln_settlement(
        {"state": "Completed", "paymentProof": REAL_PAYMENT_PROOF}
    )
    assert preimage == REAL_PREIMAGE
    assert payment_hash == REAL_PAYMENT_HASH


def test_extract_ln_settlement_accepts_camelcase_docs_shape():
    preimage, payment_hash = extract_ln_settlement(
        {
            "paymentProof": {
                "proofType": "PayoutLightningBlob",
                "preimage": REAL_PREIMAGE,
                "paymentHash": REAL_PAYMENT_HASH,
            }
        }
    )
    assert preimage == REAL_PREIMAGE
    assert payment_hash == REAL_PAYMENT_HASH


def test_extract_ln_settlement_none_for_missing_or_malformed_proof():
    assert extract_ln_settlement({}) == (None, None)
    assert extract_ln_settlement({"paymentProof": None}) == (None, None)
    assert extract_ln_settlement({"paymentProof": "opaque-proof"}) == (None, None)
    # On-chain-style proof without Lightning fields.
    assert extract_ln_settlement(
        {"paymentProof": {"proofType": "PayoutTransactionOnChainBlob", "link": "x"}}
    ) == (None, None)
    # Non-string values are never persisted.
    assert extract_ln_settlement(
        {"paymentProof": {"Preimage": 123, "PaymentHash": ["x"]}}
    ) == (None, None)


def test_real_vector_sha256_preimage_equals_payment_hash():
    """The verifiable property this feature exists for: the recorded preimage
    hashes to the recorded payment hash (checked on a real captured vector)."""
    import hashlib

    assert (
        hashlib.sha256(bytes.fromhex(REAL_PREIMAGE)).hexdigest() == REAL_PAYMENT_HASH
    )


# ── Raw payout state persistence (DB-backed) ───────────────────────────────


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


class FakePayoutClient:
    """Returns a preset payout dict for get_payout; records nothing else."""

    def __init__(self, payout: dict, **kwargs):
        self._payout = payout

    async def get_payout(self, payout_id: str) -> dict:
        return self._payout

    async def close(self) -> None:
        pass


async def _seed_split_with_payout(Session, *, payout_id: str = "payout-1") -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    async with Session() as s:
        tenant = Tenant(
            id=tenant_id,
            name=f"Acme-{uuid.uuid4().hex[:8]}",
            adapter_type="btcpay",
            btcpay_url="https://btcpay.local",
            btcpay_api_key="k",
            btcpay_store_id="store-1",
            active=True,
        )
        s.add(tenant)
        rule = SplitRule(tenant_id=tenant_id, name="Default", active=True, version=1)
        s.add(rule)
        await s.flush()
        target = SplitTarget(
            split_rule_id=rule.id, label="Alice", ln_address="alice@example.com",
            percentage=100, order=0,
        )
        s.add(target)
        payment = Payment(
            tenant_id=tenant_id, invoice_id="inv-1", amount_sats=10_000,
            status="in_progress", split_rule_id=rule.id,
        )
        s.add(payment)
        await s.flush()
        split = PaymentSplit(
            payment_id=payment.id, split_target_id=target.id, amount_sats=10_000,
            btcpay_payout_id=payout_id, status="in_progress",
        )
        s.add(split)
        await s.commit()
        return tenant_id, split.id


@pytest.mark.parametrize(
    "state,expected_status",
    [
        ("AwaitingApproval", "in_progress"),
        ("AwaitingPayment", "in_progress"),
        ("InProgress", "in_progress"),
        ("Completed", "completed"),
        ("Cancelled", "failed"),
    ],
)
@pytest.mark.asyncio
async def test_reconciliation_persists_raw_state(Session, monkeypatch, state, expected_status):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient({"id": "payout-1", "state": state}),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        # Raw state stored verbatim; mapped status unchanged from the mapping.
        assert split.btcpay_payout_state == state
        assert split.status == expected_status


@pytest.mark.asyncio
async def test_reconciliation_stores_none_when_state_absent(Session, monkeypatch):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient({"id": "payout-1"}),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        assert split.btcpay_payout_state is None


# ── Lightning settlement proof persistence (DB-backed) ─────────────────────


@pytest.mark.asyncio
async def test_reconciliation_persists_preimage_on_completed_payout(Session, monkeypatch):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient(
            {"id": "payout-1", "state": "Completed", "paymentProof": REAL_PAYMENT_PROOF}
        ),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        assert split.status == "completed"
        # Stored verbatim, exactly as BTCPay returned them.
        assert split.ln_preimage == REAL_PREIMAGE
        assert split.ln_payment_hash == REAL_PAYMENT_HASH


@pytest.mark.asyncio
async def test_reconciliation_completed_without_proof_stays_null(Session, monkeypatch):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient({"id": "payout-1", "state": "Completed"}),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        # A missing proof never blocks the money state transition.
        assert split.status == "completed"
        assert split.ln_preimage is None
        assert split.ln_payment_hash is None


@pytest.mark.asyncio
async def test_reconciliation_malformed_proof_never_breaks_completion(Session, monkeypatch):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(
        reconciliation_mod, "BTCPayClient",
        lambda **kwargs: FakePayoutClient(
            {"id": "payout-1", "state": "Completed", "paymentProof": "opaque-proof"}
        ),
    )

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        assert split.status == "completed"
        assert split.ln_preimage is None
        assert split.ln_payment_hash is None


class RaisingPayoutClient:
    """get_payout always fails — simulates BTCPay being unreachable."""

    def __init__(self, **kwargs):
        pass

    async def get_payout(self, payout_id: str) -> dict:
        raise RuntimeError("BTCPay unreachable")

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_reconciliation_survives_payout_fetch_failure(Session, monkeypatch):
    tenant_id, split_id = await _seed_split_with_payout(Session)
    monkeypatch.setattr(reconciliation_mod, "BTCPayClient", RaisingPayoutClient)

    async with Session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        # Must not raise; the failure is logged per split.
        await reconcile_tenant_payouts(s, tenant)

    async with Session() as s:
        split = (await s.execute(select(PaymentSplit).where(PaymentSplit.id == split_id))).scalar_one()
        # Money state untouched; only the check timestamp advances.
        assert split.status == "in_progress"
        assert split.ln_preimage is None
        assert split.ln_payment_hash is None
        assert split.last_checked_at is not None
