from __future__ import annotations

import os
import ssl
from dataclasses import dataclass

import httpx


def _env_key(label: str, suffix: str) -> str:
    """Build the env var name for a receiver, e.g. ('Carol', 'URL') →
    LND_RECEIVER_CAROL_URL. Labels are upper-cased and non-alphanumeric
    characters become underscores so 'Carol Doe' → CAROL_DOE."""
    slug = "".join(c if c.isalnum() else "_" for c in label.strip().upper())
    return f"LND_RECEIVER_{slug}_{suffix}"


def cert_hex_to_pem(tls_cert_hex: str) -> str:
    """Decode a hex-encoded LND tls.cert (PEM bytes) back to PEM text."""
    return bytes.fromhex(tls_cert_hex.strip()).decode("ascii")


@dataclass(frozen=True)
class LNDReceiverConfig:
    """Connection details for a recipient's own LND node (REST API).

    Loaded from local env only — never hardcoded or stored in tracked files.
    """

    label: str
    rest_url: str
    macaroon_hex: str
    tls_cert_hex: str

    @classmethod
    def from_env(
        cls, label: str, env: dict[str, str] | None = None
    ) -> "LNDReceiverConfig | None":
        """Return a config for ``label`` if all three vars are set, else None.

        A receiver is only considered "configured" when URL, macaroon and TLS
        cert are all present; a partial set returns None so the caller falls
        back to the existing Lightning-address payout path.
        """
        source = os.environ if env is None else env
        rest_url = (source.get(_env_key(label, "URL")) or "").strip()
        macaroon_hex = (source.get(_env_key(label, "MACAROON_HEX")) or "").strip()
        tls_cert_hex = (source.get(_env_key(label, "TLS_CERT_HEX")) or "").strip()
        if not (rest_url and macaroon_hex and tls_cert_hex):
            return None
        return cls(
            label=label,
            rest_url=rest_url.rstrip("/"),
            macaroon_hex=macaroon_hex,
            tls_cert_hex=tls_cert_hex,
        )


def load_lnd_receiver(
    label: str, env: dict[str, str] | None = None
) -> LNDReceiverConfig | None:
    """Convenience wrapper around :meth:`LNDReceiverConfig.from_env`."""
    return LNDReceiverConfig.from_env(label, env)


class LNDClient:
    """Minimal async client for a recipient's LND REST API.

    Used to mint a fresh BOLT11 invoice for an exact payout amount. The node's
    self-signed TLS cert is pinned via the supplied PEM (decoded from hex), and
    the invoice macaroon authorises only invoice creation.
    """

    def __init__(self, config: LNDReceiverConfig) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None

    def _ssl_context(self) -> ssl.SSLContext:
        pem = cert_hex_to_pem(self.config.tls_cert_hex)
        ctx = ssl.create_default_context(cadata=pem)
        # LND certs are commonly issued for an IP/alias rather than the REST
        # host used in a demo; pin the CA but don't require a hostname match.
        ctx.check_hostname = False
        return ctx

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                verify=self._ssl_context(),
                timeout=httpx.Timeout(15.0),
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Grpc-Metadata-macaroon": self.config.macaroon_hex}

    async def create_invoice(self, amount_sats: int, memo: str = "") -> str:
        """Create a BOLT11 invoice for ``amount_sats`` and return it.

        Raises ValueError if LND does not return a payment_request.
        """
        if amount_sats <= 0:
            raise ValueError("amount_sats must be positive")
        client = await self._get_client()
        # LND REST serialises int64 (value) as a string in JSON.
        payload: dict[str, object] = {"value": str(amount_sats)}
        if memo:
            payload["memo"] = memo
        r = await client.post(
            f"{self.config.rest_url}/v1/invoices",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        bolt11 = data.get("payment_request")
        if not bolt11:
            raise ValueError("LND did not return a payment_request")
        return bolt11

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
