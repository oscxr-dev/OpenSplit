from __future__ import annotations

from app.routers.webhooks import btcpay_invoice_amount_sats


def test_fiat_invoice_uses_settled_btc_payment_method_amount():
    invoice = {"amount": "10.80", "currency": "USD"}
    payment_methods = [
        {
            "paymentMethod": "BTC-LightningNetwork",
            "currency": "BTC",
            "paymentMethodPaid": "0.00017251",
        }
    ]

    assert btcpay_invoice_amount_sats(invoice, payment_methods) == 17251


def test_btc_invoice_amount_converts_to_sats():
    invoice = {"amount": "0.00000500", "currency": "BTC"}

    assert btcpay_invoice_amount_sats(invoice, []) == 500


def test_fiat_invoice_without_btc_payment_method_returns_zero():
    invoice = {"amount": "10.80", "currency": "USD"}

    assert btcpay_invoice_amount_sats(invoice, []) == 0
