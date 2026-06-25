from app.services.payout_reconciliation import (
    map_btcpay_payout_state,
    payout_failure_reason,
)


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
