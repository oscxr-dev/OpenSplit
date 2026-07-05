#!/usr/bin/env python3
"""Seed script: create demo tenant + admin user + import existing split rule.

Idempotent — skips if data already exists.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.database import async_session
from app.models import SplitRule, SplitTarget, Tenant, User

# ── Config from env (matching the live regtest LNBits wallets) ─────
DEMO_TENANT_NAME = os.getenv("SEED_TENANT_NAME", "bitcrew-demo")
# brand_display_name is deliberately not seeded: every display path uses
# tenant.name and the column stays dormant.
DEMO_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "oscar@admin.com")
DEMO_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", settings.seed_admin_password)

# Existing LNBits wallet IDs (from the live regtest setup)
LNBITS_URL = os.getenv("LNBITS_URL", "http://lnbits:5000")
LNBITS_ADMIN_KEY = os.getenv(
    "SEED_LNBITS_ADMIN_KEY", "10fa8174a36643799c05bd397a353021"
)
# Target wallet IDs in LNBits — read from env vars with fallbacks
# (label, wallet_id, wallet_name, percentage)
TARGET_WALLETS = [
    ("Dueño",     os.getenv("SEED_WALLET_DUENO_ID",     "971f07ec00eb4fe0be6ab3fa1efc54f9"), "Dueno",     30.0),
    ("Barista",   os.getenv("SEED_WALLET_BARISTA_ID",   "fe354fd939054fe4acd28d245837b538"), "Barista",   35.0),
    ("Proveedor", os.getenv("SEED_WALLET_PROVEEDOR_ID", "a70793520d074023b7c66bc943e2b1d0"), "Proveedor", 15.0),
    ("Impuestos", os.getenv("SEED_WALLET_IMPUESTOS_ID", "5b90f29ab655457cae03e712f815ebca"), "Impuestos", 10.0),
    ("Reserva",   os.getenv("SEED_WALLET_RESERVA_ID",   "cd8172d713c9403bb3adb66f6411602f"), "Reserva",   10.0),
]


async def seed() -> None:
    async with async_session() as session:
        # Create tenant
        result = await session.execute(
            select(Tenant).where(Tenant.name == DEMO_TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name=DEMO_TENANT_NAME,
                lnbits_admin_key=LNBITS_ADMIN_KEY,
                lnbits_url=LNBITS_URL,
            )
            session.add(tenant)
            await session.flush()
            print(f"✅ Tenant '{DEMO_TENANT_NAME}' created")
        else:
            print(f"⏭️  Tenant '{DEMO_TENANT_NAME}' already exists")

        # Create admin user
        result = await session.execute(
            select(User).where(User.email == DEMO_ADMIN_EMAIL)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=DEMO_ADMIN_EMAIL,
                password_hash=hash_password(DEMO_ADMIN_PASSWORD),
                role="admin",
            )
            session.add(user)
            await session.flush()
            print(f"✅ Admin user '{DEMO_ADMIN_EMAIL}' created")
        else:
            print(f"⏭️  Admin user '{DEMO_ADMIN_EMAIL}' already exists")

        # Create split rule
        result = await session.execute(
            select(SplitRule).where(
                SplitRule.tenant_id == tenant.id,
                SplitRule.name == "Default Split 30/35/15/10/10",
            )
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            rule = SplitRule(
                tenant_id=tenant.id,
                name="Default Split 30/35/15/10/10",
                active=True,
            )
            session.add(rule)
            await session.flush()

            for i, (label, wallet_id, wallet_name, pct) in enumerate(TARGET_WALLETS):
                session.add(SplitTarget(
                    split_rule_id=rule.id,
                    label=label,
                    lnbits_wallet_id=wallet_id,
                    lnbits_wallet_name=wallet_name,
                    percentage=pct,
                    order=i,
                ))
            await session.flush()
            print(f"✅ Split rule 'Default Split 30/35/15/10/10' created with {len(TARGET_WALLETS)} targets")
        else:
            print(f"⏭️  Split rule already exists")

        await session.commit()
        print("\n🎉 Seed complete!")
        print(f"   Login:    {DEMO_ADMIN_EMAIL}")
        print(f"   Password: {DEMO_ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
