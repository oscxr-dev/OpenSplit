from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import Tenant
from app.routers import auth, dashboard, invoices, members, payments, proof, public, splits, tenants, wallets, webhooks
from app.schemas import HealthResponse
from app.services.lnbits_client import LNBitsClient

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.services.payout_reconciliation import payout_reconciliation_loop

    # Fail fast if production is misconfigured (insecure default secrets / open CORS).
    # No-op outside production, so local dev and tests are unaffected.
    settings.enforce_production_safety()

    task = asyncio.create_task(
        payout_reconciliation_loop(settings.payout_reconcile_seconds)
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="OpenSplit Orchestrator",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(splits.router, prefix="/api/v1")
app.include_router(invoices.router, prefix="/api/v1")
app.include_router(wallets.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(members.router, prefix="/api/v1")
app.include_router(proof.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
app.include_router(public.public_teams_router, prefix="/api/v1")


# ── Health ───────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = True

    # DB check
    try:
        async for session in get_session():
            await session.execute(text("SELECT 1"))
            break
    except Exception:
        db_ok = False

    # LNBits check — LNBits is optional in the default BTCPay-first flow. It is
    # only "enabled" when a tenant is actually configured to use the lnbits
    # adapter. When no such tenant exists we report "skipped" and do NOT mark
    # the service degraded. Only an enabled-but-failing LNBits is degrading.
    lnbits_required = False
    lnbits_status = "skipped"
    try:
        async for session in get_session():
            from sqlalchemy import select
            result = await session.execute(
                select(Tenant)
                .where(Tenant.adapter_type == "lnbits", Tenant.lnbits_admin_key.is_not(None))
                .limit(1)
            )
            tenant = result.scalar_one_or_none()
            if tenant:
                lnbits_required = True
                client = LNBitsClient(tenant.lnbits_admin_key, tenant.lnbits_url)
                lnbits_status = "ok" if await client.ping() else "error"
                await client.close()
            break
    except Exception:
        # A failure only matters when LNBits is actually required.
        if lnbits_required:
            lnbits_status = "error"

    overall = "ok"
    if not db_ok:
        overall = "degraded"
    if lnbits_required and lnbits_status != "ok":
        overall = "degraded"

    return HealthResponse(status=overall, db="ok" if db_ok else "error", lnbits=lnbits_status)
