"""End-to-end test for the orchestrator API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import uuid

import httpx
import pytest
import pytest_asyncio

ORCHESTRATOR_URL = "http://localhost:8000"
DEMO_EMAIL = os.getenv("ORCHESTRATOR_TEST_EMAIL", "oscar@admin.com")
# No hardcoded password. Provide ORCHESTRATOR_TEST_PASSWORD in the environment
# to run the authenticated integration tests; otherwise they are skipped.
DEMO_PASSWORD = os.getenv("ORCHESTRATOR_TEST_PASSWORD")
WEBHOOK_SECRET = os.getenv("ORCHESTRATOR_LNBITS_WEBHOOK_SECRET", "whsec-test")


async def _login(client: httpx.AsyncClient) -> str:
    if not DEMO_PASSWORD:
        pytest.skip("Set ORCHESTRATOR_TEST_PASSWORD to run authenticated integration tests")
    r = await client.post(f"{ORCHESTRATOR_URL}/api/v1/auth/login", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
    })
    assert r.status_code == 200
    return r.json()["access_token"]


async def _tenant_health(client: httpx.AsyncClient, token: str) -> dict:
    r = await client.get(
        f"{ORCHESTRATOR_URL}/api/v1/tenants/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    return r.json()


def _sign_webhook(body: str) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_health():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORCHESTRATOR_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_flow():
    async with httpx.AsyncClient() as client:
        # Login
        token = await _login(client)
        assert token is not None

        # Protected endpoint without token
        r = await client.get(f"{ORCHESTRATOR_URL}/api/v1/tenants/me")
        assert r.status_code == 401

        # Protected endpoint with token
        data = await _tenant_health(client, token)
        assert data["lnbits_status"] in {"ok", "unreachable"}
        assert data["tenant"]["active"] is True
        assert data["tenant"]["name"]


@pytest.mark.asyncio
async def test_splits():
    async with httpx.AsyncClient() as client:
        token = await _login(client)
        r = await client.get(f"{ORCHESTRATOR_URL}/api/v1/splits",
                            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        rules = r.json()
        assert len(rules) >= 1
        active_rules = [rule for rule in rules if rule["active"]]
        assert len(active_rules) == 1
        rule = active_rules[0]
        assert rule["active"] is True
        total = sum(t["percentage"] for t in rule["targets"])
        assert abs(total - 100.0) < 0.01


@pytest.mark.asyncio
async def test_split_validation():
    async with httpx.AsyncClient() as client:
        token = await _login(client)
        # Try creating a rule that doesn't sum to 100%
        r = await client.post(
            f"{ORCHESTRATOR_URL}/api/v1/splits",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Bad Rule",
                "targets": [
                    {"label": "A", "lnbits_wallet_id": "fake1", "percentage": 60.0, "order": 0},
                    {"label": "B", "lnbits_wallet_id": "fake2", "percentage": 30.0, "order": 1},
                ],
            },
        )
        assert r.status_code == 422  # validation error


@pytest.mark.asyncio
async def test_delete_new_inactive_split_rule():
    async with httpx.AsyncClient() as client:
        token = await _login(client)
        rule_name = f"Temporary delete test {uuid.uuid4()}"
        r = await client.post(
            f"{ORCHESTRATOR_URL}/api/v1/splits",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": rule_name,
                "targets": [
                    {"label": "A", "ln_address": "a@example.com", "percentage": 60.0, "order": 0},
                    {"label": "B", "ln_address": "b@example.com", "percentage": 40.0, "order": 1},
                ],
            },
        )
        assert r.status_code == 201
        created = r.json()
        assert created["active"] is False
        assert created["can_delete"] is True

        r = await client.delete(
            f"{ORCHESTRATOR_URL}/api/v1/splits/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204

        r = await client.get(
            f"{ORCHESTRATOR_URL}/api/v1/splits",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert all(rule["id"] != created["id"] for rule in r.json())


@pytest.mark.asyncio
async def test_delete_inactive_parent_rule_without_payment_history():
    async with httpx.AsyncClient() as client:
        token = await _login(client)
        rule_name = f"Temporary parent delete test {uuid.uuid4()}"
        r = await client.post(
            f"{ORCHESTRATOR_URL}/api/v1/splits",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": rule_name,
                "targets": [
                    {"label": "A", "ln_address": "a@example.com", "percentage": 55.0, "order": 0},
                    {"label": "B", "ln_address": "b@example.com", "percentage": 45.0, "order": 1},
                ],
            },
        )
        assert r.status_code == 201
        parent = r.json()

        r = await client.patch(
            f"{ORCHESTRATOR_URL}/api/v1/splits/{parent['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"{rule_name} child"},
        )
        assert r.status_code == 200
        child = r.json()
        assert child["parent_rule_id"] == parent["id"]

        r = await client.get(
            f"{ORCHESTRATOR_URL}/api/v1/splits",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        parent_after_update = next(rule for rule in r.json() if rule["id"] == parent["id"])
        assert parent_after_update["can_delete"] is True

        r = await client.delete(
            f"{ORCHESTRATOR_URL}/api/v1/splits/{parent['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204

        r = await client.get(
            f"{ORCHESTRATOR_URL}/api/v1/splits",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        rules = r.json()
        assert all(rule["id"] != parent["id"] for rule in rules)
        child_after_delete = next(rule for rule in rules if rule["id"] == child["id"])
        assert child_after_delete["parent_rule_id"] is None

        r = await client.delete(
            f"{ORCHESTRATOR_URL}/api/v1/splits/{child['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204


@pytest.mark.asyncio
async def test_invoice_creation():
    async with httpx.AsyncClient() as client:
        token = await _login(client)
        health = await _tenant_health(client, token)
        if health["tenant"]["adapter_type"] != "lnbits":
            pytest.skip("/invoices is LNBits-only; current test tenant uses BTCPay")
        r = await client.post(
            f"{ORCHESTRATOR_URL}/api/v1/invoices",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount_sats": 5000, "memo": "Test invoice"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["amount_sats"] == 5000
        assert data["status"] == "pending"
        assert data["bolt11"] is not None


@pytest.mark.asyncio
async def test_webhook_mark_paid():
    async with httpx.AsyncClient() as client:
        token = await _login(client)
        health = await _tenant_health(client, token)
        if health["tenant"]["adapter_type"] != "lnbits":
            pytest.skip("LNBits webhook test requires an LNBits test tenant")

        # Create an invoice
        r = await client.post(
            f"{ORCHESTRATOR_URL}/api/v1/invoices",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount_sats": 5000, "memo": "Webhook test"},
        )
        assert r.status_code == 201
        inv = r.json()

        # Get the invoice_id from the DB (it's the payment_hash from LNBits)
        import asyncpg, os
        db_url = os.getenv("ORCHESTRATOR_DB_URL", "postgresql://lnbits:lnbits@postgres:5432/orchestrator")
        # Convert asyncpg URL to sync format for this one query
        pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        pg_url = pg_url.replace("postgresql+psycopg://", "postgresql://")
        conn = await asyncpg.connect(pg_url)
        row = await conn.fetchrow(
            "SELECT invoice_id FROM payments WHERE id = $1", inv["id"]
        )
        await conn.close()

        if row and row["invoice_id"]:
            inv_id = row["invoice_id"]
            body = f'{{"payment_hash": "{inv_id}", "amount": 5000000, "memo": "Webhook test"}}'
            sig = _sign_webhook(body)

            r = await client.post(
                f"{ORCHESTRATOR_URL}/api/v1/webhooks/lnbits/paid",
                content=body,
                headers={"Content-Type": "application/json", "X-LNBits-Signature": sig},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"

            # Check invoice is now paid
            r = await client.get(
                f"{ORCHESTRATOR_URL}/api/v1/invoices/{inv['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
            inv_updated = r.json()
            assert inv_updated["status"] == "paid"
            assert len(inv_updated["splits"]) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
