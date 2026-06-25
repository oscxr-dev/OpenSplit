"""Unit tests for member aggregation (pure logic, no DB)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.routers.members import MemberTargetRow, build_members, member_key


def _row(**kw) -> MemberTargetRow:
    base = dict(
        label="Alice",
        ln_address=None,
        nostr_pubkey=None,
        percentage=None,
        is_active=False,
    )
    base.update(kw)
    return MemberTargetRow(**base)


def test_member_key_uses_label_and_ln_address():
    assert member_key("Alice", "alice@ln.com") == "label:alice|addr:alice@ln.com"
    assert member_key("Alice", "  ALICE@LN.com ") == "label:alice|addr:alice@ln.com"
    assert member_key("Alice", None) == "label:alice"
    assert member_key(" Alice ", "  ") == "label:alice"


def test_collapses_targets_across_versions_by_ln_address():
    rows = [
        _row(label="Barista", ln_address="b@ln.com", percentage=30.0, is_active=False, paid_sats=100, payment_count=1),
        _row(label="Barista", ln_address="b@ln.com", percentage=35.0, is_active=True, paid_sats=200, payment_count=2),
    ]
    members = build_members(rows)
    assert len(members) == 1
    m = members[0]
    assert m.ln_address == "b@ln.com"
    assert m.target_count == 2
    assert m.total_paid_sats == 300
    assert m.payment_count == 3
    assert m.current_percentage == 35.0  # from the active rule
    assert m.collision is False


def test_same_address_with_different_labels_stays_distinct():
    rows = [
        _row(label="Barista", ln_address="x@ln.com"),
        _row(label="Owner", ln_address="x@ln.com"),
    ]
    members = build_members(rows)
    assert len(members) == 2
    assert {m.label for m in members} == {"Barista", "Owner"}
    assert all(m.target_count == 1 for m in members)


def test_fallback_to_label_when_no_ln_address():
    rows = [
        _row(label="Reserva", ln_address=None, percentage=10.0, is_active=True, paid_sats=50),
        _row(label="reserva", ln_address="", paid_sats=25),  # case/blank still collapses
    ]
    members = build_members(rows)
    assert len(members) == 1
    assert members[0].ln_address is None
    assert members[0].total_paid_sats == 75
    assert members[0].collision is False


def test_distinct_members_and_sorting_and_dates():
    d1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = [
        _row(label="Small", ln_address="s@ln.com", paid_sats=10, last_payment_at=d1, failed_count=1),
        _row(label="Big", ln_address="big@ln.com", paid_sats=999, last_payment_at=d2),
    ]
    members = build_members(rows)
    assert [m.label for m in members] == ["Big", "Small"]  # sorted by paid desc
    small = next(m for m in members if m.label == "Small")
    assert small.last_payment_at == d1
    assert small.failed_count == 1


def test_current_percentage_none_when_no_active_target():
    rows = [_row(label="Old", ln_address="o@ln.com", percentage=40.0, is_active=False)]
    members = build_members(rows)
    assert members[0].current_percentage is None
