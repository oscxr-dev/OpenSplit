from __future__ import annotations

import hashlib
import hmac

import httpx


class BTCPayClient:
    """Async client for BTCPay Server Greenfield API.

    Handles invoice creation (POS), webhook verification, and payouts
    to Lightning addresses via Pull Payments. Keys are per-tenant.
    """

    def __init__(self, base_url: str, api_key: str, store_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.store_id = store_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── Invoice (for POS / direct charge) ──────────────────────────────
    async def create_invoice(
        self, amount_sats: int, description: str = ""
    ) -> dict:
        """Create a BTCPay invoice. Amount in sats → BTC for the API."""
        client = await self._get_client()
        amount_btc = amount_sats / 100_000_000
        payload = {
            "amount": f"{amount_btc:.8f}",
            "currency": "BTC",
            "metadata": {"itemDesc": description} if description else {},
        }
        r = await client.post(
            f"{self.base_url}/api/v1/stores/{self.store_id}/invoices",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    async def get_invoice(self, invoice_id: str) -> dict:
        client = await self._get_client()
        r = await client.get(
            f"{self.base_url}/api/v1/stores/{self.store_id}/invoices/{invoice_id}",
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    async def get_invoice_payment_methods(self, invoice_id: str) -> list[dict]:
        client = await self._get_client()
        r = await client.get(
            f"{self.base_url}/api/v1/stores/{self.store_id}/invoices/{invoice_id}/payment-methods",
            headers=self._headers(),
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    # ── Webhook verification ───────────────────────────────────────────
    @staticmethod
    def verify_webhook_sig(secret: str, raw_body: bytes, sig_header: str) -> bool:
        """BTCPay signs webhooks as 'sha256=<hex>' in BTCPay-Sig header."""
        if not sig_header or not secret:
            return False
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        provided = sig_header.replace("sha256=", "").strip()
        return hmac.compare_digest(expected, provided)

    # ── Payouts via Pull Payment ───────────────────────────────────────
    async def create_pull_payment(
        self, amount_sats: int, name: str
    ) -> dict:
        """Create a pull payment the destination can claim. Returns its id."""
        client = await self._get_client()
        amount_btc = amount_sats / 100_000_000
        payload = {
            "name": name,
            "amount": f"{amount_btc:.8f}",
            "currency": "BTC",
            "payoutMethods": ["BTC-LightningNetwork"],
        }
        r = await client.post(
            f"{self.base_url}/api/v1/stores/{self.store_id}/pull-payments",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    async def payout_to_ln_address(
        self, amount_sats: int, ln_address: str, label: str = ""
    ) -> dict:
        """Direct payout to a Lightning address via the store payouts endpoint.

        Uses BTCPay's LNURL/Lightning-address payout support. The destination
        is resolved by BTCPay at processing time.
        """
        client = await self._get_client()
        amount_btc = amount_sats / 100_000_000
        payload = {
            "destination": ln_address,
            "amount": f"{amount_btc:.8f}",
            "payoutMethodId": "BTC-LightningNetwork",
            "approved": True,
            "metadata": {"label": label} if label else {},
        }
        r = await client.post(
            f"{self.base_url}/api/v1/stores/{self.store_id}/payouts",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    async def payout_to_bolt11(
        self, bolt11: str, label: str = ""
    ) -> dict:
        """Direct payout to a specific BOLT11 invoice via the store payouts
        endpoint. The amount is carried by the invoice itself, so none is sent.

        Used for dynamic LND receivers that mint a fresh invoice per payout.
        """
        client = await self._get_client()
        payload = {
            "destination": bolt11,
            "payoutMethodId": "BTC-LightningNetwork",
            "approved": True,
            "metadata": {"label": label} if label else {},
        }
        r = await client.post(
            f"{self.base_url}/api/v1/stores/{self.store_id}/payouts",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    async def get_payout(self, payout_id: str) -> dict:
        client = await self._get_client()
        r = await client.get(
            f"{self.base_url}/api/v1/stores/{self.store_id}/payouts/{payout_id}",
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    # ── Health ──────────────────────────────────────────────────────────
    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            r = await client.get(
                f"{self.base_url}/api/v1/stores/{self.store_id}",
                headers=self._headers(),
            )
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
