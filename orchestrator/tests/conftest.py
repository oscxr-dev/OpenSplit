from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture
async def anyio_backend():
    return "asyncio"
