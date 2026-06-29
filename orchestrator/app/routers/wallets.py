from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant, get_current_user
from app.database import get_session
from app.models import SplitRule, SplitTarget, Payment, PaymentSplit, Tenant, User
from app.services.lnbits_client import LNBitsClient
from pydantic import BaseModel

router = APIRouter(prefix="/wallets", tags=["wallets"])


class WalletBalanceResponse(BaseModel):
    label: str
    lnbits_wallet_id: str
    lnbits_wallet_name: str | None
    percentage: int
    accumulated_sats: int
    current_balance_sats: int | None
    color_index: int


class WalletsBalancesResponse(BaseModel):
    wallets: list[WalletBalanceResponse]
    total_accumulated_sats: int


@router.get("/balances", response_model=WalletsBalancesResponse)
async def get_wallet_balances(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> WalletsBalancesResponse:
    # 1. Get active split rule. Multiple rules can be active (board tabs); use the
    #    deterministic default (newest active) that invoice/payout creation uses.
    result = await session.execute(
        select(SplitRule)
        .where(SplitRule.tenant_id == tenant.id, SplitRule.active == True)
        .order_by(SplitRule.version.desc(), SplitRule.created_at.desc())
    )
    active_rule = result.scalars().first()
    if not active_rule:
        return WalletsBalancesResponse(wallets=[], total_accumulated_sats=0)

    # 2. Get targets
    target_result = await session.execute(
        select(SplitTarget)
        .where(SplitTarget.split_rule_id == active_rule.id)
        .order_by(SplitTarget.order)
    )
    targets = list(target_result.scalars().all())

    if not targets:
        return WalletsBalancesResponse(wallets=[], total_accumulated_sats=0)

    # 3. Get accumulated amounts from payment splits
    target_labels = [t.label for t in targets]
    accum_result = await session.execute(
        select(SplitTarget.label, func.sum(PaymentSplit.amount_sats))
        .join(SplitTarget, PaymentSplit.split_target_id == SplitTarget.id)
        .where(SplitTarget.label.in_(target_labels))
        .group_by(SplitTarget.label)
    )
    accum_map: dict[str, int] = dict(accum_result.all())

    # 4. Get current LNbits wallet balances
    try:
        client = LNBitsClient(tenant.lnbits_admin_key, tenant.lnbits_url)
        balance_map: dict[str, int | None] = {}
        for target in targets:
            wallet_id = target.lnbits_wallet_id
            if wallet_id:
                try:
                    info = await client.get_wallet()
                    balance_map[wallet_id] = info.get("balance", 0)
                except Exception:
                    balance_map[wallet_id] = None
    except Exception:
        balance_map = {}

    total = sum(accum_map.get(t.label, 0) for t in targets)

    wallets = [
        WalletBalanceResponse(
            label=t.label,
            lnbits_wallet_id=t.lnbits_wallet_id,
            lnbits_wallet_name=t.lnbits_wallet_name,
            percentage=t.percentage,
            accumulated_sats=accum_map.get(t.label, 0),
            current_balance_sats=balance_map.get(t.lnbits_wallet_id, None),
            color_index=i,
        )
        for i, t in enumerate(targets)
    ]

    return WalletsBalancesResponse(wallets=wallets, total_accumulated_sats=total)
