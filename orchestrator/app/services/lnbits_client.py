from __future__ import annotations

import httpx

from app.config import settings


class LNBitsClient:
    """Async HTTP client for LNBits API. Reads keys per-tenant, never hardcoded."""

    def __init__(self, admin_key: str, lnbits_url: str | None = None) -> None:
        self.admin_key = admin_key
        self.base_url = (lnbits_url or settings.lnbits_internal_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.admin_key, "Content-Type": "application/json"}

    # ── Wallet ────────────────────────────────────────────────────────
    async def get_wallet(self) -> dict:
        client = await self._get_client()
        r = await client.get(f"{self.base_url}/api/v1/wallet", headers=self._headers())
        r.raise_for_status()
        return r.json()

    # ── Invoice ───────────────────────────────────────────────────────
    async def create_invoice(self, amount_sats: int, memo: str = "", webhook_url: str | None = None) -> dict:
        client = await self._get_client()
        payload = {"out": False, "amount": amount_sats, "memo": memo, "unit": "sat"}
        if webhook_url:
            payload["webhook"] = webhook_url
        r = await client.post(
            f"{self.base_url}/api/v1/payments",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    # ── Payment / transfer ────────────────────────────────────────────
    async def pay_invoice(self, bolt11: str) -> dict:
        client = await self._get_client()
        r = await client.post(
            f"{self.base_url}/api/v1/payments",
            headers=self._headers(),
            json={"out": True, "bolt11": bolt11},
        )
        r.raise_for_status()
        return r.json()

    async def transfer_between_wallets(
        self, from_wallet_key: str, to_wallet_key: str, amount_sats: int, memo: str = ""
    ) -> dict:
        """Internal transfer: create invoice on target, pay from source."""
        target_client = LNBitsClient(to_wallet_key, self.base_url)
        invoice = await target_client.create_invoice(amount_sats, memo)
        bolt11 = invoice.get("payment_request")
        if not bolt11:
            raise ValueError("LNBits did not return a BOLT11 invoice for transfer")
        return await self.pay_invoice(bolt11)

    # ── Invoice status check ─────────────────────────────────────────
    async def check_invoice(self, payment_hash: str) -> dict | None:
        """Check if a payment has been received (paid) in LNBits.
        Returns payment dict if found and paid, None if pending or not found."""
        client = await self._get_client()
        try:
            r = await client.get(
                f"{self.base_url}/api/v1/payments/{payment_hash}",
                headers=self._headers(),
            )
            if r.status_code != 200:
                return None
            data = r.json()
            # LNBits returns {"paid": true, "details": {"pending": false}}
            is_paid = data.get("paid") is True
            details = data.get("details", {})
            is_pending = details.get("pending", True)
            if is_paid and not is_pending:
                return data
            return None
        except Exception:
            return None

    async def list_payments(self, limit: int = 50) -> list[dict]:
        """List recent payments from LNBits."""
        client = await self._get_client()
        try:
            r = await client.get(
                f"{self.base_url}/api/v1/payments?limit={limit}",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return []

    # ── Health ────────────────────────────────────────────────────────
    # ── Wallet lookup by name ──────────────────────────────────────────
    _wallet_cache: dict[str, str] | None = None
    _wallet_cache_ts: float = 0
    WALLET_CACHE_TTL = 300  # 5 minutes

    async def resolve_wallet_id(self, wallet_name: str) -> str | None:
        """Resolve LNBits wallet ID by name. Uses cache with 5min TTL.

        In LNBits, wallet names are not guaranteed unique (multiple wallets
        can share the same name). This function returns the FIRST match
        found, preferring wallets whose name matches exactly.

        Returns None if no wallet with that name exists."""
        import time

        now = time.time()
        if self._wallet_cache is None or (now - self._wallet_cache_ts) > self.WALLET_CACHE_TTL:
            await self._refresh_wallet_cache()

        return (self._wallet_cache or {}).get(wallet_name)

    async def _refresh_wallet_cache(self) -> None:
        """Fetch all wallets from LNBits and build name→id map.
        If duplicates exist, the first one wins."""
        import time

        client = await self._get_client()
        try:
            r = await client.get(
                f"{self.base_url}/usermanager/api/v1/wallets",
                headers=self._headers(),
            )
            if r.status_code != 200:
                return
            wallets = r.json()
            self._wallet_cache = {}
            for w in wallets:
                name = w.get("name", "")
                wid = w.get("id", "")
                # First match wins (prefer existing mapping)
                if name and wid and name not in self._wallet_cache:
                    self._wallet_cache[name] = wid
            self._wallet_cache_ts = time.time()
        except Exception:
            pass

    # ── Health ────────────────────────────────────────────────────────
    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            r = await client.get(f"{self.base_url}/api/v1/wallet", headers=self._headers())
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
