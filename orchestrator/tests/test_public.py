"""Unit tests for public transparency assembly (pure logic, no DB).

These focus on the privacy contract: amounts gated by show_amounts and no
private fields ever present on the public schema.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.routers.public import (
    PublicPaymentRow,
    PublicRuleRow,
    PublicTargetRow,
    build_public_view,
)
from app.schemas import (
    PublicRecentPayment,
    PublicSplitRule,
    PublicSplitMember,
    PublicTransparencyResponse,
)

_TARGETS = [
    PublicTargetRow(label="Barista", nostr_pubkey=None, percentage=60.0),
    PublicTargetRow(label=None, nostr_pubkey="npub1xyz", percentage=40.0),
]
_PAYMENTS = [
    PublicPaymentRow(status="paid", paid_at=datetime(2026, 6, 1, tzinfo=timezone.utc), amount_sats=1000),
    PublicPaymentRow(status="paid", paid_at=datetime(2026, 5, 1, tzinfo=timezone.utc), amount_sats=500),
]


def test_distribution_carries_only_public_identity_and_percentage():
    view = build_public_view(
        name="Coffee Co", slug="coffee", show_amounts=True,
        targets=_TARGETS, payments=[], total_paid_sats=0,
    )
    assert view.name == "Coffee Co"
    assert view.slug == "coffee"
    assert [m.label for m in view.distribution] == ["Barista", None]
    assert [m.nostr_pubkey for m in view.distribution] == [None, "npub1xyz"]
    assert [m.percentage for m in view.distribution] == [60.0, 40.0]


def test_public_rules_carry_only_public_rule_metadata():
    view = build_public_view(
        name="Coffee Co",
        slug="coffee",
        show_amounts=True,
        targets=_TARGETS,
        payments=[],
        total_paid_sats=0,
        public_rules=[
            PublicRuleRow(
                name="Weekend split",
                version=3,
                completed_split_count=4,
                targets=_TARGETS,
            )
        ],
    )
    assert len(view.public_rules) == 1
    rule = view.public_rules[0]
    assert rule.name == "Weekend split"
    assert rule.version == 3
    assert rule.completed_split_count == 4
    assert [member.percentage for member in rule.distribution] == [60.0, 40.0]


def test_amounts_shown_when_show_amounts_true():
    view = build_public_view(
        name="Coffee Co", slug="coffee", show_amounts=True,
        targets=_TARGETS, payments=_PAYMENTS, total_paid_sats=1500,
    )
    assert view.show_amounts is True
    assert [p.amount_sats for p in view.recent_payments] == [1000, 500]
    assert view.total_sats == 1500


def test_amounts_hidden_when_show_amounts_false():
    view = build_public_view(
        name="Coffee Co", slug="coffee", show_amounts=False,
        targets=_TARGETS, payments=_PAYMENTS, total_paid_sats=1500,
    )
    assert view.show_amounts is False
    # Statuses still visible, but every amount is suppressed.
    assert [p.status for p in view.recent_payments] == ["paid", "paid"]
    assert all(p.amount_sats is None for p in view.recent_payments)
    assert view.total_sats is None


def test_public_schemas_expose_no_private_fields():
    # The public schema surface must not contain any private/secret field names.
    forbidden = {
        "ln_address", "payout_id", "btcpay_payout_id", "bolt11", "memo",
        "id", "tenant_id", "split_target_id", "split_rule_id", "invoice_id",
        "api_key", "btcpay_api_key", "lnbits_admin_key", "store_id",
        "btcpay_store_id", "webhook_secret", "btcpay_webhook_secret", "email",
    }
    for model in (PublicTransparencyResponse, PublicSplitRule, PublicSplitMember, PublicRecentPayment):
        leaked = forbidden & set(model.model_fields)
        assert not leaked, f"{model.__name__} exposes private fields: {leaked}"


def test_serialized_payload_contains_no_private_values():
    view = build_public_view(
        name="Coffee Co", slug="coffee", show_amounts=True,
        targets=_TARGETS, payments=_PAYMENTS, total_paid_sats=1500,
    )
    dumped = view.model_dump()
    assert set(dumped.keys()) == {
        "name", "slug", "show_amounts", "public_rules", "distribution", "recent_payments", "total_sats",
    }
    assert dumped["public_rules"] == []
    for member in dumped["distribution"]:
        assert set(member.keys()) == {"label", "nostr_pubkey", "percentage"}
    for payment in dumped["recent_payments"]:
        assert set(payment.keys()) == {"status", "paid_at", "amount_sats"}
