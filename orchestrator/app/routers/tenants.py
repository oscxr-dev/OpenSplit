from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import Tenant, User
from app.schemas import TenantHealth, TenantResponse, TenantUpdate
from app.services.btcpay_client import BTCPayClient
from app.services.lnbits_client import LNBitsClient

router = APIRouter(prefix="/tenants", tags=["tenants"])


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

    return TenantHealth(
        tenant=TenantResponse.model_validate(tenant),
        lnbits_status="ok" if connection_ok else "unreachable",
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
    await session.commit()
    await session.refresh(tenant)
    return TenantResponse.model_validate(tenant)
