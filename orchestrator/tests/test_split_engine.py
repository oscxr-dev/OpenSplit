"""Property-based tests for split arithmetic — largest remainder algorithm."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

import pytest
from hypothesis import given, settings, strategies as st

from app.services.split_engine import calculate_splits


# ── Helpers ──────────────────────────────────────────────────────────
@dataclass
class FakeTarget:
    """Lightweight stand-in for SplitTarget in tests."""
    id: uuid.UUID
    label: str
    percentage: float
    order: int
    lnbits_wallet_id: str = ""


def make_targets(percentages: list[float]) -> list[FakeTarget]:
    return [
        FakeTarget(id=uuid.uuid4(), label=f"T{i}", percentage=p, order=i)
        for i, p in enumerate(percentages)
    ]


# ── Edge Cases ───────────────────────────────────────────────────────
def test_p5_regression_12345_sats():
    """P5: 12,345 sats with 30/35/15/10/10 — must sum exactly."""
    targets = make_targets([30, 35, 15, 10, 10])
    splits = calculate_splits(12345, targets)
    amounts = [s for _, s in splits]

    assert sum(amounts) == 12345, f"Got {amounts}, sum={sum(amounts)}"
    # Expected: largest fractions get the extra sats
    # 30% → 3703.5 → floor 3703, fraction .5  → gets +1 = 3704
    # 35% → 4320.75 → floor 4320, fraction .75 → gets +1 = 4321
    # 15% → 1851.75 → floor 1851, fraction .75 → gets +1 = 1852
    # 10% → 1234.5 → floor 1234, fraction .5  → tiebreak by order (lower wins)
    # 10% → 1234.5 → floor 1234, fraction .5  → no extra
    # Remainder = 12345 - (3703+4320+1851+1234+1234) = 12345 - 12342 = 3
    # Top 3 fractions: .75 (T1), .75 (T2), .5 (T0 wins tiebreak by lower order)
    assert amounts == [3704, 4321, 1852, 1234, 1234], f"Unexpected split: {amounts}"


def test_exact_division_no_remainder():
    """When amount divides cleanly, no remainder correction needed."""
    targets = make_targets([50, 25, 25])
    splits = calculate_splits(10000, targets)
    amounts = [s for _, s in splits]
    assert amounts == [5000, 2500, 2500]
    assert sum(amounts) == 10000


def test_single_target():
    """100% to one target."""
    targets = make_targets([100])
    splits = calculate_splits(99999, targets)
    amounts = [s for _, s in splits]
    assert amounts == [99999]
    assert sum(amounts) == 99999


def test_tiny_amount():
    """1 sat with multiple targets — only first gets it."""
    targets = make_targets([50, 30, 20])
    splits = calculate_splits(1, targets)
    amounts = [s for _, s in splits]
    assert sum(amounts) == 1
    assert amounts[0] == 1  # T0 (50% = 0.5, largest fraction)


def test_all_targets_equal():
    """Equal percentages, prime amount."""
    targets = make_targets([25, 25, 25, 25])
    splits = calculate_splits(7, targets)
    amounts = [s for _, s in splits]
    assert sum(amounts) == 7
    # 25% of 7 = 1.75 → floor 1 each, total 4, remainder 3
    # All fractions equal (.75), tiebreak by lower order → T0, T1, T2 get +1
    assert amounts == [2, 2, 2, 1]


def test_five_targets_various_amounts():
    """Broad test: 5 targets, various amounts."""
    targets = make_targets([30, 35, 15, 10, 10])
    for amount in [1, 2, 5, 10, 100, 1000, 9999, 12345, 1_000_000]:
        splits = calculate_splits(amount, targets)
        amounts = [s for _, s in splits]
        assert sum(amounts) == amount, f"Failed for {amount}: sum={sum(amounts)}"
        assert all(a >= 0 for a in amounts)
        assert len(amounts) == 5


def test_amount_zero_raises():
    """Zero amount must raise ValueError."""
    targets = make_targets([50, 50])
    with pytest.raises(ValueError):
        calculate_splits(0, targets)


def test_negative_amount_raises():
    targets = make_targets([50, 50])
    with pytest.raises(ValueError):
        calculate_splits(-100, targets)


def test_percentages_not_100_raises():
    targets = make_targets([30, 30, 30])  # 90%
    with pytest.raises(ValueError):
        calculate_splits(1000, targets)


# ── Property-Based Tests ─────────────────────────────────────────────
@st.composite
def valid_targets(draw):
    """Generate a list of percentages that sum to exactly 100 (using Decimal)."""
    n = draw(st.integers(min_value=1, max_value=10))
    raw = draw(st.lists(st.integers(min_value=1, max_value=99), min_size=n, max_size=n))
    total = Decimal(sum(raw))
    # Round to 2 decimal places (DB Numeric(5,2) precision)
    pcts = [round(float(Decimal(p) * Decimal(100) / total), 2) for p in raw]
    # Adjust last to make sum exactly 100.0 at 2dp
    diff = round(100.0 - sum(pcts[:-1]), 2)
    percentages = pcts[:-1] + [diff]
    return make_targets(percentages)


@given(amount=st.integers(min_value=1, max_value=10_000_000), targets=valid_targets())
@settings(max_examples=500)
def test_property_sum_equals_amount(amount, targets):
    """For ANY amount and ANY valid percentage set, splits sum to amount."""
    splits = calculate_splits(amount, targets)
    amounts = [s for _, s in splits]
    assert sum(amounts) == amount, (
        f"amount={amount} splits={amounts} sum={sum(amounts)} "
        f"pcts={[t.percentage for t in targets]}"
    )


@given(amount=st.integers(min_value=1, max_value=10_000_000), targets=valid_targets())
@settings(max_examples=500)
def test_property_all_non_negative(amount, targets):
    """All splits must be ≥ 0."""
    splits = calculate_splits(amount, targets)
    for target, s in splits:
        assert s >= 0, f"Negative split for {target.label}: {s}"


@given(amount=st.integers(min_value=1, max_value=10_000_000), targets=valid_targets())
@settings(max_examples=500)
def test_property_same_length(amount, targets):
    """Result has same number of elements as targets."""
    splits = calculate_splits(amount, targets)
    assert len(splits) == len(targets)


@given(
    amount=st.integers(min_value=1, max_value=1_000_000),
    targets=valid_targets(),
)
@settings(max_examples=500)
def test_property_remainder_correct(amount, targets):
    """Each split is floor(amount * pct / 100) plus at most 1 extra sat."""
    splits = calculate_splits(amount, targets)
    for (target, s), t in zip(splits, targets):
        exact = Decimal(amount) * Decimal(str(t.percentage)) / Decimal("100")
        floor = int(exact.to_integral_value(rounding=ROUND_DOWN))
        assert s in (floor, floor + 1), (
            f"target={t.label} pct={t.percentage} amount={amount} "
            f"exact={exact} floor={floor} got={s}"
        )
