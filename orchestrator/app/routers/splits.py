from __future__ import annotations

from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant, get_current_user
from app.core.percentages import quantized_total
from app.database import get_session
from app.models import Payment, PaymentSplit, SplitRule, SplitTarget, Tenant, User
from app.schemas import SplitRuleCreate, SplitRuleResponse, SplitRuleUpdate, SplitTargetCreate, SplitTargetSchema
from app.services.lnd_client import load_lnd_receiver

router = APIRouter(prefix="/splits", tags=["splits"])

logger = structlog.get_logger(__name__)


def _is_meaningful_ln_address(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip()
    if " " in text or "@" not in text:
        return False
    local, domain = text.split("@", 1)
    return bool(local and domain and "." in domain)


def _has_lnd_receiver(label: str | None) -> bool:
    """A target with a configured dynamic LND receiver (matching its label)
    mints its own invoice at payout time, so it doesn't need a Lightning
    address. Reads local env only — see lnd_client.load_lnd_receiver."""
    if not label:
        return False
    return load_lnd_receiver(label) is not None


def _is_meaningful_wallet_id(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip()
    return len(text) >= 16 and any(ch.isalpha() for ch in text)


def _validate_target_destinations(targets: list[SplitTargetCreate], tenant: Tenant) -> None:
    errors: list[str] = []
    for index, target in enumerate(targets, start=1):
        if tenant.adapter_type == "btcpay":
            if not (
                _is_meaningful_ln_address(target.ln_address)
                or _has_lnd_receiver(target.label)
            ):
                errors.append(f"target {index} ({target.label}) needs a valid Lightning address")
        elif tenant.adapter_type == "lnbits":
            if not _is_meaningful_wallet_id(target.lnbits_wallet_id):
                errors.append(f"target {index} ({target.label}) needs a valid LNbits wallet id")
        elif not (
            _is_meaningful_ln_address(target.ln_address)
            or _is_meaningful_wallet_id(target.lnbits_wallet_id)
        ):
            errors.append(f"target {index} ({target.label}) needs a valid recipient")

    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)


def _superseding_active_rule(
    rule: SplitRule, active_rules: list[SplitRule]
) -> SplitRule | None:
    """Return an active rule that supersedes ``rule`` (same lineage — i.e. same
    name — but a newer version), if any.

    Activating an older, superseded version would silently "revert" the active
    rule (e.g. a stale dashboard tab re-activating an old version). The activate
    endpoint refuses that so the newest active rule stays put.
    """
    for other in active_rules:
        if other.id == rule.id:
            continue
        if other.name == rule.name and other.version > rule.version:
            return other
    return None


def _validate_existing_rule_targets(targets: list[SplitTarget], tenant: Tenant) -> None:
    total = quantized_total(
        t.percentage for t in targets if float(t.percentage or 0) > 0
    )
    if total != Decimal("100"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Active non-zero targets must sum to 100%, got {total}%",
        )

    errors: list[str] = []
    for index, target in enumerate([t for t in targets if float(t.percentage or 0) > 0], start=1):
        if (
            tenant.adapter_type == "btcpay"
            and not _is_meaningful_ln_address(target.ln_address)
            and not _has_lnd_receiver(target.label)
        ):
            errors.append(f"target {index} ({target.label}) needs a valid Lightning address")
        elif tenant.adapter_type == "lnbits" and not _is_meaningful_wallet_id(target.lnbits_wallet_id):
            errors.append(f"target {index} ({target.label}) needs a valid LNbits wallet id")

    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)


async def _build_response(rule: SplitRule, session: AsyncSession) -> SplitRuleResponse:
    result = await session.execute(
        select(SplitTarget).where(SplitTarget.split_rule_id == rule.id).order_by(SplitTarget.order)
    )
    targets = list(result.scalars().all())
    can_delete = await _can_delete_rule(rule, targets, session)
    target_schemas = [
        SplitTargetSchema.model_validate(target).model_copy(
            update={"has_lnd_receiver": _has_lnd_receiver(target.label)}
        )
        for target in targets
    ]
    return SplitRuleResponse(
        id=rule.id,
        name=rule.name,
        active=rule.active,
        version=rule.version,
        parent_rule_id=rule.parent_rule_id,
        targets=target_schemas,
        created_at=rule.created_at,
        can_delete=can_delete,
    )


async def _can_delete_rule(rule: SplitRule, targets: list[SplitTarget], session: AsyncSession) -> bool:
    if rule.active:
        return False

    payment_count = (
        await session.execute(
            select(func.count()).select_from(Payment).where(Payment.split_rule_id == rule.id)
        )
    ).scalar_one()
    if payment_count:
        return False

    target_ids = [target.id for target in targets]
    if not target_ids:
        return True

    split_count = (
        await session.execute(
            select(func.count())
            .select_from(PaymentSplit)
            .where(PaymentSplit.split_target_id.in_(target_ids))
        )
    ).scalar_one()
    return split_count == 0


@router.get("", response_model=list[SplitRuleResponse])
async def list_splits(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> list[SplitRuleResponse]:
    result = await session.execute(
        select(SplitRule).where(SplitRule.tenant_id == tenant.id).order_by(SplitRule.created_at.desc())
    )
    rules = result.scalars().all()
    return [await _build_response(r, session) for r in rules]


@router.post("", response_model=SplitRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_split(
    body: SplitRuleCreate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> SplitRuleResponse:
    _validate_target_destinations(body.targets, tenant)

    rule = SplitRule(tenant_id=tenant.id, name=body.name, active=False)
    session.add(rule)
    await session.flush()

    for i, t in enumerate(body.targets):
        session.add(SplitTarget(
            split_rule_id=rule.id,
            label=t.label,
            lnbits_wallet_id=t.lnbits_wallet_id,
            lnbits_wallet_name=t.lnbits_wallet_name or t.label,
            ln_address=t.ln_address,
            percentage=t.percentage,
            order=t.order or i,
        ))

    await session.commit()
    return await _build_response(rule, session)


@router.patch("/{rule_id}", response_model=SplitRuleResponse)
async def update_split(
    rule_id: str,
    body: SplitRuleUpdate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> SplitRuleResponse:
    result = await session.execute(
        select(SplitRule).where(SplitRule.id == rule_id, SplitRule.tenant_id == tenant.id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split rule not found")

    # Rules are immutable once created because PaymentSplit rows retain FKs to
    # their targets. Editing always creates a new version and preserves history.
    source_targets_result = await session.execute(
        select(SplitTarget)
        .where(SplitTarget.split_rule_id == rule.id)
        .order_by(SplitTarget.order)
    )
    source_targets = list(source_targets_result.scalars().all())
    new_rule = SplitRule(
        tenant_id=tenant.id,
        name=body.name or rule.name,
        active=rule.active,
        version=rule.version + 1,
        parent_rule_id=rule.id,
    )
    session.add(new_rule)
    await session.flush()

    targets = body.targets
    if targets is not None:
        _validate_target_destinations(targets, tenant)

    targets_to_write = targets if targets is not None else source_targets

    for i, target in enumerate(targets_to_write):
        session.add(
            SplitTarget(
                split_rule_id=new_rule.id,
                label=target.label,
                lnbits_wallet_id=target.lnbits_wallet_id,
                lnbits_wallet_name=target.lnbits_wallet_name or target.label,
                ln_address=target.ln_address,
                percentage=float(target.percentage),
                order=target.order if target.order is not None else i,
            )
        )

    if rule.active:
        rule.active = False

    await session.commit()
    return await _build_response(new_rule, session)


@router.post("/{rule_id}/activate", response_model=SplitRuleResponse)
async def activate_split(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> SplitRuleResponse:
    result = await session.execute(
        select(SplitRule).where(SplitRule.id == rule_id, SplitRule.tenant_id == tenant.id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split rule not found")

    target_result = await session.execute(
        select(SplitTarget).where(SplitTarget.split_rule_id == rule.id).order_by(SplitTarget.order)
    )
    _validate_existing_rule_targets(list(target_result.scalars().all()), tenant)

    all_rules = list(
        (
            await session.execute(
                select(SplitRule).where(SplitRule.tenant_id == tenant.id)
            )
        ).scalars().all()
    )

    # Safeguard: don't let a stale/duplicate client revert the active rule to an
    # older version of the same lineage. Activating the newest version (or a
    # genuinely different rule) is always allowed.
    active_rules = [r for r in all_rules if r.active]
    superseding = _superseding_active_rule(rule, active_rules)
    if superseding is not None:
        logger.warning(
            "split_activate_blocked_supersede",
            tenant_id=str(tenant.id),
            requested_rule_id=str(rule.id),
            requested_version=rule.version,
            active_rule_id=str(superseding.id),
            active_version=superseding.version,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{rule.name}' v{rule.version} is superseded by the active "
                f"v{superseding.version}. Activate the newest version or edit it instead."
            ),
        )

    # Deactivate all other rules for this tenant
    for other in all_rules:
        if other.id != rule.id:
            other.active = False

    rule.active = True
    await session.commit()
    logger.info(
        "split_activated",
        tenant_id=str(tenant.id),
        rule_id=str(rule.id),
        version=rule.version,
        name=rule.name,
    )
    return await _build_response(rule, session)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_split(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(
        select(SplitRule).where(SplitRule.id == rule_id, SplitRule.tenant_id == tenant.id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split rule not found")

    target_result = await session.execute(
        select(SplitTarget).where(SplitTarget.split_rule_id == rule.id).order_by(SplitTarget.order)
    )
    targets = list(target_result.scalars().all())
    if not await _can_delete_rule(rule, targets, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only inactive split rules without payment history can be deleted",
        )

    await session.execute(
        update(SplitRule)
        .where(SplitRule.parent_rule_id == rule.id)
        .values(parent_rule_id=None)
    )

    for target in targets:
        await session.delete(target)
    await session.delete(rule)
    await session.commit()
