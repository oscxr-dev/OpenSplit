"""Property and known-vector tests for the rule fingerprint (pure, no DB).

The canonical serialization in app/services/proof_hash.py is a compatibility
contract — once fingerprints are signed, a digest must be reproducible byte
for byte, forever. The frozen known-vector test below is the tripwire: if it
fails, the contract changed and every previously stored fingerprint is
orphaned. Never "fix" the expected digest; fix the code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from decimal import Decimal

from hypothesis import given, strategies as st

from app.services.proof_hash import canonical_rule_json, rule_fingerprint


@dataclass(frozen=True)
class FakeRule:
    name: str
    version: int


@dataclass(frozen=True)
class FakeTarget:
    label: str
    percentage: object
    order: int
    ln_address: str | None = None
    lnbits_wallet_id: str | None = None


# ── Frozen known vector — the contract tripwire ──────────────────────
KNOWN_RULE = FakeRule(name="Café split", version=3)
KNOWN_TARGETS = [
    FakeTarget(label="Barista", percentage=60, order=0, ln_address="barista@walletofsatoshi.com"),
    FakeTarget(label="Owner", percentage=39.5, order=1, ln_address="owner@getalby.com"),
    FakeTarget(label="Tip jar", percentage="0.5", order=2, lnbits_wallet_id="wallet-tipjar-01"),
]
KNOWN_CANONICAL = (
    '{"name":"Café split","targets":['
    '{"identity":"barista@walletofsatoshi.com","label":"Barista","order":0,"percentage":"60.00"},'
    '{"identity":"owner@getalby.com","label":"Owner","order":1,"percentage":"39.50"},'
    '{"identity":"wallet-tipjar-01","label":"Tip jar","order":2,"percentage":"0.50"}'
    '],"version":3}'
)
KNOWN_DIGEST = "bc0c49b1591b2d47dbaf19324e09fdf78517114e314b4346ed39cb5397b322aa"


def test_known_vector_canonical_json_is_frozen():
    assert canonical_rule_json(KNOWN_RULE, KNOWN_TARGETS) == KNOWN_CANONICAL


def test_known_vector_digest_is_frozen():
    assert rule_fingerprint(KNOWN_RULE, KNOWN_TARGETS) == KNOWN_DIGEST


def test_digest_is_sha256_of_canonical_utf8():
    import hashlib

    assert (
        hashlib.sha256(KNOWN_CANONICAL.encode("utf-8")).hexdigest() == KNOWN_DIGEST
    )


# ── Hypothesis strategies ────────────────────────────────────────────
_text = st.text(min_size=1, max_size=40)
# NUMERIC(5,2)-representable percentages: 0.00–100.00 in whole cents.
_pct = st.integers(min_value=0, max_value=10_000).map(lambda c: Decimal(c) / 100)


def _targets_strategy():
    return st.lists(
        st.builds(
            FakeTarget,
            label=_text,
            percentage=_pct,
            order=st.integers(min_value=0, max_value=50),
            ln_address=st.one_of(st.none(), _text),
            lnbits_wallet_id=st.one_of(st.none(), _text),
        ),
        min_size=1,
        max_size=8,
        # Unique order values so a swap in the sensitivity tests is meaningful
        # and the canonical sort has a single stable outcome.
        unique_by=lambda t: t.order,
    )


_rule = st.builds(FakeRule, name=_text, version=st.integers(min_value=1, max_value=1000))


# ── Determinism ──────────────────────────────────────────────────────
@given(rule=_rule, targets=_targets_strategy())
def test_same_input_same_digest(rule, targets):
    assert rule_fingerprint(rule, targets) == rule_fingerprint(rule, targets)
    digest = rule_fingerprint(rule, targets)
    assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")


@given(rule=_rule, targets=_targets_strategy(), seed=st.randoms())
def test_list_order_does_not_matter(rule, targets, seed):
    """The digest depends on the stored ``order`` field, not DB row order."""
    shuffled = list(targets)
    seed.shuffle(shuffled)
    assert rule_fingerprint(rule, targets) == rule_fingerprint(rule, shuffled)


@given(rule=_rule, targets=_targets_strategy())
def test_equivalent_percentage_representations_match(rule, targets):
    """float / str / Decimal spellings of the same 2-decimal value agree."""
    as_str = [replace(t, percentage=str(t.percentage)) for t in targets]
    as_float = [replace(t, percentage=float(t.percentage)) for t in targets]
    assert (
        rule_fingerprint(rule, targets)
        == rule_fingerprint(rule, as_str)
        == rule_fingerprint(rule, as_float)
    )


# ── Sensitivity: every economic field moves the digest ───────────────
@given(rule=_rule, targets=_targets_strategy())
def test_percentage_nudge_changes_digest(rule, targets):
    nudged = [replace(targets[0], percentage=Decimal(str(targets[0].percentage)) + Decimal("0.01"))]
    nudged += targets[1:]
    assert rule_fingerprint(rule, targets) != rule_fingerprint(rule, nudged)


@given(rule=_rule, targets=_targets_strategy())
def test_label_change_changes_digest(rule, targets):
    renamed = [replace(targets[0], label=targets[0].label + "x")] + targets[1:]
    assert rule_fingerprint(rule, targets) != rule_fingerprint(rule, renamed)


@given(rule=_rule, targets=_targets_strategy())
def test_identity_change_changes_digest(rule, targets):
    prior = targets[0].ln_address or ""
    swapped = [replace(targets[0], ln_address=prior + "x@example.com")] + targets[1:]
    assert rule_fingerprint(rule, targets) != rule_fingerprint(rule, swapped)


@given(rule=_rule, targets=_targets_strategy())
def test_order_swap_changes_digest(rule, targets):
    """Swapping two targets' stored order values re-orders the rule → new digest.

    Only meaningful when the swapped targets differ in some serialized field,
    so pin two targets that are guaranteed distinct."""
    a = replace(targets[0], label="uniq-a", order=0)
    b = replace(targets[0], label="uniq-b", order=1)
    rest = [replace(t, order=t.order + 2) for t in targets[1:]]
    swapped_a, swapped_b = replace(a, order=1), replace(b, order=0)
    assert rule_fingerprint(rule, [a, b] + rest) != rule_fingerprint(
        rule, [swapped_a, swapped_b] + rest
    )


@given(rule=_rule, targets=_targets_strategy())
def test_rule_name_and_version_change_digest(rule, targets):
    base = rule_fingerprint(rule, targets)
    assert base != rule_fingerprint(replace(rule, name=rule.name + "x"), targets)
    assert base != rule_fingerprint(replace(rule, version=rule.version + 1), targets)


# ── Canonical-form invariants ────────────────────────────────────────
@given(rule=_rule, targets=_targets_strategy())
def test_canonical_json_is_compact_sorted_and_parseable(rule, targets):
    canonical = canonical_rule_json(rule, targets)
    doc = json.loads(canonical)
    # Re-encoding under the contract's own rules reproduces the exact string.
    assert (
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        == canonical
    )
    # Every percentage is a two-decimal string, never a JSON number.
    for entry in doc["targets"]:
        assert isinstance(entry["percentage"], str)
        whole, frac = entry["percentage"].split(".")
        assert len(frac) == 2
