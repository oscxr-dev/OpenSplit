from __future__ import annotations

import pytest
import pytest_asyncio

from app.config import settings


@pytest_asyncio.fixture
async def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_default_relay_publishing(monkeypatch):
    """Tests must never reach real public relays.

    The shipped ORCHESTRATOR_NOSTR_RELAYS default is deliberately non-empty,
    so without this guard every sign-endpoint test would broadcast its test
    event to the live Nostr network. Publish tests opt back in with fakes by
    monkeypatching settings.nostr_relays themselves.
    """
    monkeypatch.setattr(settings, "nostr_relays", [])
