"""Unit tests for split-proof assembly (pure logic, no DB)."""

from __future__ import annotations

import uuid

from app.routers.proof import ProofSplitRow, build_proof


def _row(**kw) -> ProofSplitRow:
    base = dict(
        split_id=uuid.uuid4(),
        split_target_id=uuid.uuid4(),
        label="Barista",
        ln_address="barista@ln.com",
        nostr_pubkey=None,
        percentage=50.0,
        amount_sats=500,
        payout_status="completed",
        payout_id=None,
    )
    base.update(kw)
    return ProofSplitRow(**base)


def test_proof_balanced_when_splits_sum_to_payment():
    pid = uuid.uuid4()
    rows = [
        _row(label="Barista", percentage=60.0, amount_sats=600),
        _row(label="Owner", percentage=40.0, amount_sats=400),
    ]
    proof = build_proof(
        payment_id=pid,
        amount_sats=1000,
        status="paid",
        split_rule_id=None,
        split_rule_version=3,
        rows=rows,
    )
    assert proof.payment_id == pid
    assert proof.amount_sats == 1000
    assert proof.status == "paid"
    assert proof.split_rule_version == 3
    assert len(proof.members) == 2
    assert proof.integrity.split_sum_sats == 1000
    assert proof.integrity.payment_amount_sats == 1000
    assert proof.integrity.difference_sats == 0
    assert proof.integrity.balanced is True


def test_proof_unbalanced_when_splits_do_not_sum():
    rows = [_row(amount_sats=300), _row(amount_sats=300)]
    proof = build_proof(
        payment_id=uuid.uuid4(),
        amount_sats=1000,
        status="paid",
        split_rule_id=None,
        split_rule_version=None,
        rows=rows,
    )
    assert proof.integrity.split_sum_sats == 600
    assert proof.integrity.difference_sats == 400
    assert proof.integrity.balanced is False


def test_proof_carries_member_fields_including_payout():
    sid = uuid.uuid4()
    rows = [
        _row(
            split_id=sid,
            label="Reserve",
            ln_address="reserve@ln.com",
            nostr_pubkey="npub1abc",
            percentage=25.0,
            amount_sats=250,
            payout_status="in_progress",
            payout_id="payout-xyz",
        )
    ]
    proof = build_proof(
        payment_id=uuid.uuid4(),
        amount_sats=250,
        status="paid",
        split_rule_id=None,
        split_rule_version=1,
        rows=rows,
    )
    m = proof.members[0]
    assert m.split_id == sid
    assert m.label == "Reserve"
    assert m.ln_address == "reserve@ln.com"
    assert m.nostr_pubkey == "npub1abc"
    assert m.percentage == 25.0
    assert m.amount_sats == 250
    assert m.payout_status == "in_progress"
    assert m.payout_id == "payout-xyz"
    assert proof.integrity.balanced is True


def test_proof_with_no_splits_is_unbalanced_unless_zero_amount():
    empty = build_proof(
        payment_id=uuid.uuid4(),
        amount_sats=100,
        status="pending",
        split_rule_id=None,
        split_rule_version=None,
        rows=[],
    )
    assert empty.members == []
    assert empty.integrity.split_sum_sats == 0
    assert empty.integrity.difference_sats == 100
    assert empty.integrity.balanced is False

    zero = build_proof(
        payment_id=uuid.uuid4(),
        amount_sats=0,
        status="pending",
        split_rule_id=None,
        split_rule_version=None,
        rows=[],
    )
    assert zero.integrity.balanced is True
