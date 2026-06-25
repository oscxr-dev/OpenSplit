#!/usr/bin/env python3
"""Provision the demo tenant for a BTCPay (Polar + BTCPay + Zeus) demo.

This is a *configuration* helper only. It writes nothing but tenant /
split_rule / split_target rows. It does NOT touch the split engine, webhook
handler, payout logic, reconciliation worker, migrations, or the dashboard —
it just sets the per-tenant BTCPay credentials and an active split rule so the
existing BTCPay webhook path can run end to end.

Idempotent: safe to run repeatedly. Re-running with the same DEMO_TARGETS_JSON
reuses the existing active rule instead of creating duplicates.

Required env vars
-----------------
  BTCPAY_URL              e.g. http://host.docker.internal:14142
  BTCPAY_API_KEY          BTCPay Greenfield API key (store-scoped)
  BTCPAY_STORE_ID         BTCPay store id
  BTCPAY_WEBHOOK_SECRET   shared secret used to verify BTCPay-Sig
  DEMO_TARGETS_JSON       JSON array of targets, each:
                            {"label": "Barista",
                             "ln_address": "barista@lnurl.regtest",
                             "percentage": 60,
                             "nostr_pubkey": "npub1...",   # optional
                             "order": 0}                    # optional

Optional env vars
-----------------
  SEED_TENANT_NAME        tenant to configure (default: bitcrew-demo)
  DEMO_RULE_NAME          split rule name      (default: BTCPay Demo Split)
  ORCHESTRATOR_PUBLIC_URL base URL BTCPay will call
                          (default: http://host.docker.internal:8000)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import SplitRule, SplitTarget, Tenant

SEED_TENANT_NAME = os.getenv("SEED_TENANT_NAME", "bitcrew-demo")
DEMO_RULE_NAME = os.getenv("DEMO_RULE_NAME", "BTCPay Demo Split")
ORCHESTRATOR_PUBLIC_URL = os.getenv(
    "ORCHESTRATOR_PUBLIC_URL", "http://host.docker.internal:8000"
).rstrip("/")

_REQUIRED_BTCPAY_VARS = (
    "BTCPAY_URL",
    "BTCPAY_API_KEY",
    "BTCPAY_STORE_ID",
    "BTCPAY_WEBHOOK_SECRET",
)


class ConfigError(Exception):
    """Raised for any operator-facing misconfiguration (clean exit, no stack)."""


def _fail(message: str) -> "None":
    raise ConfigError(message)


def _load_btcpay_env() -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in _REQUIRED_BTCPAY_VARS:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            missing.append(name)
        values[name] = raw
    if missing:
        _fail(
            "Missing required env var(s): "
            + ", ".join(missing)
            + "\nSet BTCPAY_URL, BTCPAY_API_KEY, BTCPAY_STORE_ID and "
            "BTCPAY_WEBHOOK_SECRET before running."
        )
    return values


def _parse_targets() -> list[dict]:
    raw = (os.getenv("DEMO_TARGETS_JSON") or "").strip()
    if not raw:
        _fail(
            "DEMO_TARGETS_JSON is required. Example:\n"
            '  DEMO_TARGETS_JSON=\'[{"label":"Barista","ln_address":'
            '"barista@lnurl.regtest","percentage":60,"order":0},'
            '{"label":"Owner","ln_address":"owner@lnurl.regtest",'
            '"percentage":40,"order":1}]\''
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"DEMO_TARGETS_JSON is not valid JSON: {exc}")
    if not isinstance(parsed, list) or not parsed:
        _fail("DEMO_TARGETS_JSON must be a non-empty JSON array of targets.")

    targets: list[dict] = []
    total = Decimal("0")
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            _fail(f"Target #{i} must be a JSON object.")
        label = str(item.get("label") or "").strip()
        ln_address = str(item.get("ln_address") or "").strip()
        if not label:
            _fail(f"Target #{i} is missing 'label'.")
        if not ln_address:
            _fail(
                f"Target '{label or i}' is missing 'ln_address'. Every BTCPay "
                "target must have a Lightning address or its payout fails."
            )
        if "percentage" not in item:
            _fail(f"Target '{label}' is missing 'percentage'.")
        try:
            percentage = float(item["percentage"])
        except (TypeError, ValueError):
            _fail(f"Target '{label}' has a non-numeric 'percentage'.")
        if percentage <= 0:
            _fail(f"Target '{label}' percentage must be > 0.")
        nostr = item.get("nostr_pubkey")
        order = item.get("order", i)
        try:
            order = int(order)
        except (TypeError, ValueError):
            _fail(f"Target '{label}' has a non-integer 'order'.")
        targets.append(
            {
                "label": label,
                "ln_address": ln_address,
                "percentage": round(percentage, 2),
                "nostr_pubkey": (str(nostr).strip() or None) if nostr else None,
                "order": order,
            }
        )
        total += Decimal(str(round(percentage, 2)))

    if total != Decimal("100"):
        _fail(f"Target percentages must sum to 100, got {total}.")
    targets.sort(key=lambda t: t["order"])
    return targets


def _targets_match(existing: list[SplitTarget], desired: list[dict]) -> bool:
    """True when an existing rule's targets already equal the desired set."""
    if len(existing) != len(desired):
        return False
    existing_sorted = sorted(existing, key=lambda t: t.order)
    for cur, want in zip(existing_sorted, desired):
        if (cur.label or "") != want["label"]:
            return False
        if (cur.ln_address or "") != want["ln_address"]:
            return False
        if float(cur.percentage) != float(want["percentage"]):
            return False
        if (cur.nostr_pubkey or None) != want["nostr_pubkey"]:
            return False
    return True


async def _activate_only(session: AsyncSession, tenant_id, rule_id) -> None:
    """Make rule_id the single active rule for the tenant."""
    result = await session.execute(
        select(SplitRule).where(SplitRule.tenant_id == tenant_id)
    )
    for rule in result.scalars().all():
        rule.active = rule.id == rule_id


async def seed_btcpay_demo() -> None:
    btcpay = _load_btcpay_env()
    desired = _parse_targets()

    async with async_session() as session:
        # 1. Existing demo tenant (created by scripts/seed.py) — required.
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.name == SEED_TENANT_NAME)
            )
        ).scalar_one_or_none()
        if tenant is None:
            _fail(
                f"Tenant '{SEED_TENANT_NAME}' not found. Run scripts/seed.py "
                "first (or set SEED_TENANT_NAME to an existing tenant)."
            )

        # 2. Apply BTCPay configuration (idempotent — just sets the columns).
        tenant.adapter_type = "btcpay"
        tenant.btcpay_url = btcpay["BTCPAY_URL"]
        tenant.btcpay_api_key = btcpay["BTCPAY_API_KEY"]
        tenant.btcpay_store_id = btcpay["BTCPAY_STORE_ID"]
        tenant.btcpay_webhook_secret = btcpay["BTCPAY_WEBHOOK_SECRET"]

        # 3. Find existing demo rules for this tenant (newest version first).
        existing_rules = list(
            (
                await session.execute(
                    select(SplitRule)
                    .where(
                        SplitRule.tenant_id == tenant.id,
                        SplitRule.name == DEMO_RULE_NAME,
                    )
                    .order_by(SplitRule.version.desc())
                )
            ).scalars().all()
        )

        reused = False
        target_rule: SplitRule
        if existing_rules:
            latest = existing_rules[0]
            latest_targets = list(
                (
                    await session.execute(
                        select(SplitTarget).where(
                            SplitTarget.split_rule_id == latest.id
                        )
                    )
                ).scalars().all()
            )
            if _targets_match(latest_targets, desired):
                target_rule = latest
                reused = True

        if not reused:
            # Create a new rule version (never mutate historical targets —
            # PaymentSplit rows keep FKs to them).
            next_version = (
                max((r.version for r in existing_rules), default=0) + 1
            )
            parent_id = existing_rules[0].id if existing_rules else None
            target_rule = SplitRule(
                tenant_id=tenant.id,
                name=DEMO_RULE_NAME,
                active=True,
                version=next_version,
                parent_rule_id=parent_id,
            )
            session.add(target_rule)
            await session.flush()
            for i, t in enumerate(desired):
                session.add(
                    SplitTarget(
                        split_rule_id=target_rule.id,
                        label=t["label"],
                        lnbits_wallet_id=None,
                        lnbits_wallet_name=t["label"],
                        ln_address=t["ln_address"],
                        nostr_pubkey=t["nostr_pubkey"],
                        percentage=t["percentage"],
                        order=t["order"] if t["order"] is not None else i,
                    )
                )

        # 4. Ensure this rule is the only active one.
        await _activate_only(session, tenant.id, target_rule.id)
        await session.commit()
        await session.refresh(tenant)

        webhook_url = (
            f"{ORCHESTRATOR_PUBLIC_URL}/api/v1/webhooks/btcpay/{tenant.id}"
        )

        print("\n🎉 BTCPay demo tenant ready\n")
        print(f"   Tenant        : {tenant.name}")
        print(f"   Tenant ID     : {tenant.id}")
        print(f"   Adapter       : {tenant.adapter_type}")
        print(f"   BTCPay URL    : {tenant.btcpay_url}")
        print(f"   Store ID      : {tenant.btcpay_store_id}")
        print(
            f"   Split rule    : {target_rule.name} v{target_rule.version} "
            f"({'reused' if reused else 'created'}, active)"
        )
        for t in desired:
            print(f"                   - {t['label']}: {t['percentage']}% → {t['ln_address']}")
        print("\n   ── Paste into BTCPay → Store → Settings → Webhooks ──")
        print(f"   Payload URL   : {webhook_url}")
        print(f"   Secret        : {tenant.btcpay_webhook_secret}")
        print('   Event         : "An invoice has been settled" (InvoiceSettled)\n')


def main() -> int:
    try:
        asyncio.run(seed_btcpay_demo())
    except ConfigError as exc:
        print(f"\n❌ {exc}\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
