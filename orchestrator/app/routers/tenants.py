from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Payment, PaymentSplit, SplitRule, Tenant, User
from app.schemas import (
    BTCPayAuthorizeUrl,
    BTCPayConnectionTest,
    BTCPayWebhookSecret,
    TenantHealth,
    TenantResponse,
    TenantStatusActiveRule,
    TenantStatusResponse,
    TenantUpdate,
)
from app.services.btcpay_client import BTCPayClient
from app.services.lnbits_client import LNBitsClient

router = APIRouter(prefix="/tenants", tags=["tenants"])

# Raw BTCPay payout states that mean "BTCPay is holding this payout and needs a
# manual send or a payout processor" — the pipeline can't clear them on its own.
WAITING_BTCPAY_STATES = {"AwaitingApproval", "AwaitingPayment"}
# A waiting payout is only surfaced once it has sat this long; younger ones are
# still normal in-flight delivery.
WAITING_IN_BTCPAY_THRESHOLD = timedelta(minutes=3)
# A failed split counts toward "failing" only if it failed within this window.
RECENT_FAILURE_WINDOW = timedelta(hours=24)
# Split statuses that need no further delivery work.
_TERMINAL_SPLIT_STATUSES = {"completed", "failed", "cancelled"}

# BTCPay's payout-method id for Lightning payouts (matches payout_to_ln_address
# and create_pull_payment). A payout processor tagged with this method is the
# one that auto-sends OpenSplit's Lightning payouts.
LIGHTNING_PAYOUT_METHOD_ID = "BTC-LightningNetwork"

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

# The events the operator must select in BTCPay's Create Webhook form — the
# only ones webhooks.py acts on (both mark an invoice as settled).
BTCPAY_WEBHOOK_EVENTS = ["InvoiceSettled", "InvoicePaymentSettled"]


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
    if body.public_show_amounts is not None:
        tenant.public_show_amounts = body.public_show_amounts
    if body.public_country is not None:
        tenant.public_country = body.public_country
    if body.public_city is not None:
        tenant.public_city = body.public_city
    # Nostr public key: presence in the request (not None-ness) decides, so an
    # explicitly sent blank clears the stored key while an omitted field never
    # touches it. The schema already normalized npub→hex and rejected nsec.
    if "nostr_pubkey" in body.model_fields_set:
        tenant.nostr_pubkey = body.nostr_pubkey
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


@router.post("/me/btcpay/webhook-secret", response_model=BTCPayWebhookSecret)
async def generate_btcpay_webhook_secret(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> BTCPayWebhookSecret:
    """Generate (or regenerate) the tenant's BTCPay webhook secret.

    This response is the only time the secret is ever readable. Regenerating
    overwrites the stored secret — deliveries signed with the old one are
    rejected from now on — and resets last_webhook_at, so the dashboard drops
    back to "waiting for first webhook" until BTCPay delivers with the new
    secret.
    """
    secret = secrets.token_urlsafe(32)
    tenant.btcpay_webhook_secret = secret
    tenant.last_webhook_at = None
    await session.commit()
    return BTCPayWebhookSecret(
        secret=secret,
        webhook_url=f"{settings.public_base_url}/api/v1/webhooks/btcpay/{tenant.id}",
        events=list(BTCPAY_WEBHOOK_EVENTS),
    )


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


# ── Aggregate pipeline status (read-only) ──────────────────────────────────


@dataclass
class SplitDeliveryFact:
    """The only per-split fields the payout_delivery check needs. Timestamps are
    timezone-aware (columns are DateTime(timezone=True))."""

    status: str
    btcpay_payout_state: str | None
    executed_at: datetime | None
    updated_at: datetime | None


def compute_store_status(*, configured: bool, reachable: bool | None) -> str:
    """"not_configured" until all three BTCPay creds are set, then the probe
    result. ``reachable`` is only consulted when configured."""
    if not configured:
        return "not_configured"
    return "ok" if reachable else "unreachable"


def compute_webhook_status(*, secret_set: bool, last_webhook_at: datetime | None) -> str:
    """"not_configured" with no secret, "waiting" until the first signature-valid
    delivery lands, "verified" once one has."""
    if not secret_set:
        return "not_configured"
    return "verified" if last_webhook_at is not None else "waiting"


def compute_payout_delivery(facts: list[SplitDeliveryFact], now: datetime) -> str:
    """Roll every split's delivery state into one label. Precedence, most urgent
    first: a recent failure ("failing") outranks a payout stuck in BTCPay
    ("waiting_in_btcpay"), which outranks normal in-flight delivery
    ("delivering"); nothing outstanding is "idle"."""
    if any(
        fact.status == "failed"
        and fact.updated_at is not None
        and now - fact.updated_at <= RECENT_FAILURE_WINDOW
        for fact in facts
    ):
        return "failing"

    non_terminal = [fact for fact in facts if fact.status not in _TERMINAL_SPLIT_STATUSES]
    if any(
        fact.btcpay_payout_state in WAITING_BTCPAY_STATES
        and fact.executed_at is not None
        and now - fact.executed_at > WAITING_IN_BTCPAY_THRESHOLD
        for fact in non_terminal
    ):
        return "waiting_in_btcpay"

    if non_terminal:
        return "delivering"
    return "idle"


def compute_lightning_payout_processor(processors: list[dict] | None) -> str:
    """Roll the store's payout-processor list into an auto-send state.

    - "active"  — a processor for Lightning is configured (payouts auto-send).
    - "missing" — the list was fetched but has no Lightning processor.
    - "unknown" — the list couldn't be read (key lacks the permission, store
                  unreachable, unexpected shape). Never guess "missing" here:
                  "can't tell" must not read as "definitely not configured".

    BTCPay tags each processor with a payout-method id; older/newer builds have
    used ``payoutMethodId`` and ``paymentMethod``, so accept either.
    """
    if processors is None:
        return "unknown"
    for proc in processors:
        if not isinstance(proc, dict):
            continue
        method = proc.get("payoutMethodId") or proc.get("paymentMethod")
        if method == LIGHTNING_PAYOUT_METHOD_ID:
            return "active"
    return "missing"


@router.get("/me/status", response_model=TenantStatusResponse)
async def get_tenant_status(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> TenantStatusResponse:
    """One-call health snapshot for the dashboard status strip. Read-only:
    reuses the existing BTCPay probe and never writes."""
    now = datetime.now(timezone.utc)

    store_configured = bool(
        tenant.btcpay_url and tenant.btcpay_api_key and tenant.btcpay_store_id
    )
    reachable: bool | None = None
    # Only probe the payout processor when the store is reachable; otherwise we
    # genuinely can't tell ("unknown").
    lightning_payout_processor = "unknown"
    if store_configured:
        client = BTCPayClient(
            tenant.btcpay_url or "",
            tenant.btcpay_api_key or "",
            tenant.btcpay_store_id or "",
            timeout=BTCPAY_TEST_TIMEOUT_SECONDS,
        )
        try:
            reachable = await client.ping()
            if reachable:
                processors = await client.get_payout_processors()
                lightning_payout_processor = compute_lightning_payout_processor(
                    processors
                )
        finally:
            await client.close()

    # Newest active rule (matches the invoice-creation default: highest version,
    # then most recently created).
    active_rule_row = (
        await session.execute(
            select(SplitRule.name, SplitRule.version)
            .where(SplitRule.tenant_id == tenant.id, SplitRule.active.is_(True))
            .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
        )
    ).first()
    active_rule = (
        TenantStatusActiveRule(name=active_rule_row.name, version=active_rule_row.version)
        if active_rule_row is not None
        else None
    )

    # Fetch only the splits the payout_delivery check can care about: everything
    # still in flight, plus failures recent enough to count.
    delivery_rows = (
        await session.execute(
            select(
                PaymentSplit.status,
                PaymentSplit.btcpay_payout_state,
                PaymentSplit.executed_at,
                PaymentSplit.updated_at,
            )
            .join(Payment, Payment.id == PaymentSplit.payment_id)
            .where(
                Payment.tenant_id == tenant.id,
                or_(
                    PaymentSplit.status.not_in(_TERMINAL_SPLIT_STATUSES),
                    and_(
                        PaymentSplit.status == "failed",
                        PaymentSplit.updated_at >= now - RECENT_FAILURE_WINDOW,
                    ),
                ),
            )
        )
    ).all()
    facts = [
        SplitDeliveryFact(
            status=row.status,
            btcpay_payout_state=row.btcpay_payout_state,
            executed_at=row.executed_at,
            updated_at=row.updated_at,
        )
        for row in delivery_rows
    ]

    return TenantStatusResponse(
        store=compute_store_status(configured=store_configured, reachable=reachable),
        webhook=compute_webhook_status(
            secret_set=bool(tenant.btcpay_webhook_secret),
            last_webhook_at=tenant.last_webhook_at,
        ),
        active_rule=active_rule,
        payout_delivery=compute_payout_delivery(facts, now),
        lightning_payout_processor=lightning_payout_processor,
        public_page="on" if tenant.public_transparency_enabled else "off",
    )
