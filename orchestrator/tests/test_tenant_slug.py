"""TenantUpdate.public_slug is normalized to a lowercase, URL-safe slug.

Pure schema-level tests — no DB or network.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import TenantUpdate


def test_public_slug_normalized_from_store_name():
    assert TenantUpdate(public_slug="Oscar Shop's").public_slug == "oscar-shops"


def test_public_slug_lowercased_and_spaces_replaced():
    assert TenantUpdate(public_slug="  Hello World  ").public_slug == "hello-world"
    assert TenantUpdate(public_slug="BitCrew").public_slug == "bitcrew"


def test_public_slug_passthrough_when_already_clean():
    assert TenantUpdate(public_slug="oscar-shops").public_slug == "oscar-shops"


def test_public_slug_none_is_left_untouched():
    assert TenantUpdate(public_slug=None).public_slug is None
    assert TenantUpdate().public_slug is None


def test_public_slug_with_no_alphanumerics_is_rejected():
    with pytest.raises(ValidationError):
        TenantUpdate(public_slug="!!!  ---")
