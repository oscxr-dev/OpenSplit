from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Tenant, User
from app.schemas import (
    BTCPayAuthorizeUrl,
    BTCPayConnectionTest,
    TenantHealth,
    TenantResponse,
    TenantUpdate,
)
from app.services.btcpay_client import BTCPayClient
from app.services.lnbits_client import LNBitsClient

router = APIRouter(prefix="/tenants", tags=["tenants"])

# Minimal BTCPay Greenfield permissions OpenSplit actually uses
# (see services/btcpay_client.py):
#   cancreateinvoice      → POST /stores/{id}/invoices (POS charges)
#   canviewinvoices       → GET invoice + payment methods (settled amounts)
#   canmanagepullpayments → pull payments + create/approve/read payouts
#   canviewstoresettings  → GET /stores/{id} (connection check)
BTCPAY_MINIMAL_PERMISSIONS = [
    "btcpay.store.cancreateinvoice",
    "btcpay.store.canviewinvoices",
    "btcpay.store.canmanagepullpayments",
    "btcpay.store.canviewstoresettings",
]

# Probe timeout: a connection check should answer fast, not hang for the
# client's default 20s.
BTCPAY_TEST_TIMEOUT_SECONDS = 10.0


def interpret_store_probe(status_code: int | None) -> BTCPayConnectionTest:
    """Map the GET /stores/{id} probe outcome to granular checks.

    ``status_code=None`` means the server could not be reached at all (connect
    error, DNS failure, TLS failure, or timeout). Pure and side-effect free.
    Detail strings are fixed sentences — never interpolate exception text or
    credentials into them.
    """
    if status_code is None:
        return BTCPayConnectionTest(
            url_reachable=False,
            auth_ok=None,
            store_found=None,
            ok=False,
            detail="Could not reach the BTCPay server. Check the URL and that the server is running.",
        )
    if status_code in (401, 403):
        # 403 also covers a store-scoped key probing a store it cannot see
        # (BTCPay hides those instead of 404ing), so mention both causes.
        return BTCPayConnectionTest(
            url_reachable=True,
            auth_ok=False,
            store_found=None,
            ok=False,
            detail="BTCPay rejected the API key. Check the key and that it has access to this store ID.",
        )
    if status_code == 404:
        return BTCPayConnectionTest(
            url_reachable=True,
            auth_ok=True,
            store_found=False,
            ok=False,
            detail="The API key works but the store was not found. Copy the store ID from your BTCPay store settings.",
        )
    if status_code == 200:
        return BTCPayConnectionTest(
            url_reachable=True,
            auth_ok=True,
            store_found=True,
            ok=True,
            detail="Connected. Server, API key, and store all check out.",
        )
    return BTCPayConnectionTest(
        url_reachable=True,
        auth_ok=None,
        store_found=None,
        ok=False,
        detail=f"BTCPay answered with unexpected status {status_code}. Check the server URL points at BTCPay.",
    )


@router.get("/me", response_model=TenantHealth)
async def get_my_tenant(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> TenantHealth:
    if tenant.adapter_type == "btcpay":
        client = BTCPayClient(
            tenant.btcpay_url or "",
            tenant.btcpay_api_key or "",
            tenant.btcpay_store_id or "",
        )
    else:
        client = LNBitsClient(tenant.lnbits_admin_key or "", tenant.lnbits_url)
    connection_ok = await client.ping()
    await client.close()

    connection_status = "ok" if connection_ok else "unreachable"
    return TenantHealth(
        tenant=TenantResponse.model_validate(tenant),
        connection_status=connection_status,
        lnbits_status=connection_status,
    )


@router.patch("/me", response_model=TenantResponse)
async def update_my_tenant(
    body: TenantUpdate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> TenantResponse:
    if body.name is not None:
        tenant.name = body.name
    if body.lnbits_url is not None:
        tenant.lnbits_url = body.lnbits_url
    if body.public_slug is not None:
        # Already normalized (lowercase, url-safe) by the schema validator.
        tenant.public_slug = body.public_slug
    if body.public_transparency_enabled is not None:
        tenant.public_transparency_enabled = body.public_transparency_enabled
    if body.public_country is not None:
        tenant.public_country = body.public_country
    if body.public_city is not None:
        tenant.public_city = body.public_city
    # BTCPay connection fields. The schema turns blank strings into None, so a
    # blank input can never wipe a stored value (PATCH: omitted = unchanged).
    if body.btcpay_url is not None:
        tenant.btcpay_url = body.btcpay_url
    if body.btcpay_api_key is not None:
        tenant.btcpay_api_key = body.btcpay_api_key
    if body.btcpay_store_id is not None:
        tenant.btcpay_store_id = body.btcpay_store_id
    await session.commit()
    await session.refresh(tenant)
    return TenantResponse.model_validate(tenant)


@router.post("/me/btcpay/test", response_model=BTCPayConnectionTest)
async def btcpay_connection_test(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> BTCPayConnectionTest:
    """Read-only connection probe against BTCPay (single GET, never writes)."""
    missing = [
        label
        for label, value in (
            ("server URL", tenant.btcpay_url),
            ("API key", tenant.btcpay_api_key),
            ("store ID", tenant.btcpay_store_id),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"BTCPay {', '.join(missing)} not configured yet",
        )

    client = BTCPayClient(
        tenant.btcpay_url,
        tenant.btcpay_api_key,
        tenant.btcpay_store_id,
        timeout=BTCPAY_TEST_TIMEOUT_SECONDS,
    )
    try:
        status_code: int | None = (await client.get_store_response()).status_code
    except Exception:
        # Connect errors, DNS/TLS failures, timeouts, malformed URLs. The
        # exception is deliberately not logged or echoed: its repr can carry
        # request details and detail strings must stay credential-free.
        status_code = None
    finally:
        await client.close()
    return interpret_store_probe(status_code)


@router.get("/me/btcpay/authorize-url", response_model=BTCPayAuthorizeUrl)
async def get_btcpay_authorize_url(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> BTCPayAuthorizeUrl:
    """Deep link to BTCPay's API-key authorize screen with OpenSplit's minimal
    permission set preselected. The operator approves it in BTCPay and pastes
    the generated key back into Settings."""
    if not tenant.btcpay_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Set the BTCPay server URL first",
        )
    query = urlencode(
        {
            "applicationName": "OpenSplit",
            "selectiveStores": "true",
            "permissions": BTCPAY_MINIMAL_PERMISSIONS,
        },
        doseq=True,
    )
    return BTCPayAuthorizeUrl(
        authorize_url=f"{tenant.btcpay_url}/api-keys/authorize?{query}",
        permissions=list(BTCPAY_MINIMAL_PERMISSIONS),
    )
