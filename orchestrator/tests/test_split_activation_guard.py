"""Unit tests for the activate-supersede safeguard.

Ensures an older version of a rule lineage cannot be activated while a newer
version is already active (which is what caused the active rule to "revert"
from v5 Carol/Dave back to v4 Oscar/Ricardo/COGS when a stale client re-issued
an activate for the old version).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.routers.splits import _superseding_active_rule


@dataclass
class FakeRule:
    name: str
    version: int
    active: bool = False
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def test_activating_older_version_is_blocked_when_newer_is_active():
    v4 = FakeRule(name="BitCrew", version=4, active=False)
    v5 = FakeRule(name="BitCrew", version=5, active=True)

    superseding = _superseding_active_rule(v4, [v5])

    assert superseding is v5  # v4 cannot steal active from the newer v5


def test_activating_newest_version_is_allowed():
    v4 = FakeRule(name="BitCrew", version=4, active=True)
    v5 = FakeRule(name="BitCrew", version=5, active=False)

    # Activating the newer v5 while v4 is active is fine.
    assert _superseding_active_rule(v5, [v4]) is None


def test_reactivating_the_current_rule_is_allowed():
    v5 = FakeRule(name="BitCrew", version=5, active=True)

    # The rule that is already active is not superseded by itself.
    assert _superseding_active_rule(v5, [v5]) is None


def test_different_lineage_is_not_blocked():
    other_active = FakeRule(name="Holiday Promo", version=9, active=True)
    bitcrew_v5 = FakeRule(name="BitCrew", version=5, active=False)

    # A differently-named rule never supersedes; activation is allowed.
    assert _superseding_active_rule(bitcrew_v5, [other_active]) is None


def test_no_active_rule_means_anything_can_activate():
    v4 = FakeRule(name="BitCrew", version=4, active=False)

    assert _superseding_active_rule(v4, []) is None
