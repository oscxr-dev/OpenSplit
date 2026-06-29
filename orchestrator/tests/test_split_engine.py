"""Property-based tests for split arithmetic — largest remainder algorithm."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

import pytest
from hypothesis import given, settings, strategies as st

from app.services.split_engine import calculate_split_allocation, calculate_splits


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
    allocation = calculate_split_allocation(10000, targets)
    amounts = [s for _, s in allocation.splits]
    assert amounts == [5000, 2500, 2500]
    assert sum(amounts) == 10000
    assert allocation.unallocated_store_sats == 0
    assert allocation.pending_remainder_sats == 0


def test_101_sats_50_50_largest_remainder_tie_by_order():
    """101 sats at 50/50 floors to 50/50; the extra sat goes to lower order."""
    targets = make_targets([50, 50])
    allocation = calculate_split_allocation(101, targets)
    amounts = [s for _, s in allocation.splits]
    assert amounts == [51, 50]
    assert sum(amounts) == 101
    assert allocation.pending_remainder_sats == 0


def test_100_sats_33_33_34():
    targets = make_targets([33, 33, 34])
    allocation = calculate_split_allocation(100, targets)
    amounts = [s for _, s in allocation.splits]
    assert amounts == [33, 33, 34]
    assert sum(amounts) == 100
    assert allocation.pending_remainder_sats == 0


def test_single_target():
    """100% to one target."""
    targets = make_targets([100])
    splits = calculate_splits(99999, targets)
    amounts = [s for _, s in splits]
    assert amounts == [99999]
    assert sum(amounts) == 99999


def test_tiny_amount():
    """1 sat with multiple targets is too small to pay only one winner."""
    targets = make_targets([50, 30, 20])
    allocation = calculate_split_allocation(1, targets)
    amounts = [s for _, s in allocation.splits]
    assert amounts == [0, 0, 0]
    assert sum(amounts) == 0
    assert allocation.pending_remainder_sats == 1


def test_one_sat_across_three_targets_no_fractional_sats():
    """For a 100% rule, 1 sat across 3 targets stays pending."""
    targets = make_targets([33.33, 33.33, 33.34])
    allocation = calculate_split_allocation(1, targets)
    amounts = [s for _, s in allocation.splits]
    assert amounts == [0, 0, 0]
    assert sum(amounts) == 0
    assert allocation.unallocated_store_sats == 0
    assert allocation.pending_remainder_sats == 1
    assert all(isinstance(amount, int) for amount in amounts)


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
        allocation = calculate_split_allocation(amount, targets)
        amounts = [s for _, s in allocation.splits]
        assert sum(amounts) + allocation.pending_remainder_sats == amount, (
            f"Failed for {amount}: splits={amounts} pending={allocation.pending_remainder_sats}"
        )
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


def test_percentages_over_100_raises():
    targets = make_targets([60, 60])  # 120%
    with pytest.raises(ValueError):
        calculate_splits(1000, targets)


def test_zero_total_raises():
    targets = make_targets([0])
    with pytest.raises(ValueError):
        calculate_splits(1000, targets)


def test_partial_split_allocates_only_configured_share():
    """A rule totalling < 100% pays out only the configured share; the rest
    (the unallocated remainder) stays in the store and is not distributed."""
    targets = make_targets([20, 20, 20])  # 60% total
    allocation = calculate_split_allocation(100, targets)
    amounts = [amt for _, amt in allocation.splits]
    assert amounts == [20, 20, 20]
    assert sum(amounts) == 60  # only 60% allocated
    assert allocation.unallocated_store_sats == 40  # 40% stays in store
    assert allocation.pending_remainder_sats == 0


def test_partial_split_with_rounding_stays_within_allocation():
    """With awkward percentages the allocated sats never exceed amount*total/100."""
    targets = make_targets([10, 10, 10])  # 30% total
    allocation = calculate_split_allocation(1007, targets)
    amounts = [amt for _, amt in allocation.splits]
    # floor(1007 * 30 / 100) = 302 allocated, distributed across the three targets
    assert sum(amounts) == 302
    assert allocation.unallocated_store_sats == 704
    assert allocation.pending_remainder_sats == 1
    assert all(a >= 0 for a in amounts)


def test_one_sat_partial_rule_keeps_indivisible_dust_pending():
    """If target+store floors cannot consume a whole sat, keep it pending.

    For 1 sat at 60% total allocation, target share is 0.6 sat and store share
    is 0.4 sat. Neither can honestly receive a fractional sat, so no payout is
    created and the whole sat is tracked as pending remainder.
    """
    targets = make_targets([20, 20, 20])
    allocation = calculate_split_allocation(1, targets)
    amounts = [amt for _, amt in allocation.splits]
    assert amounts == [0, 0, 0]
    assert allocation.allocated_sats == 0
    assert allocation.unallocated_store_sats == 0
    assert allocation.pending_remainder_sats == 1


def test_tie_breaks_by_target_id_when_order_is_equal():
    """Equal fractional remainders are deterministic even if order collides."""
    targets = [
        FakeTarget(
            id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            label="High id",
            percentage=50,
            order=0,
        ),
        FakeTarget(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            label="Low id",
            percentage=50,
            order=0,
        ),
    ]
    allocation = calculate_split_allocation(101, targets)
    amounts = [amt for _, amt in allocation.splits]
    assert amounts == [50, 51]


def test_split_amounts_are_always_integer_sats():
    targets = make_targets([12.5, 12.5, 25, 50])
    allocation = calculate_split_allocation(999, targets)
    amounts = [amt for _, amt in allocation.splits]
    assert all(isinstance(amount, int) for amount in amounts)
    assert all(amount >= 0 for amount in amounts)


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
    """For 100% rules, splits plus pending remainder sum to amount."""
    allocation = calculate_split_allocation(amount, targets)
    amounts = [s for _, s in allocation.splits]
    assert sum(amounts) + allocation.pending_remainder_sats == amount, (
        f"amount={amount} splits={amounts} pending={allocation.pending_remainder_sats} "
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
    allocation = calculate_split_allocation(amount, targets)
    if allocation.allocated_sats == 0 and allocation.pending_remainder_sats > 0:
        assert all(s == 0 for _, s in allocation.splits)
        return

    for (target, s), t in zip(allocation.splits, targets):
        exact = Decimal(amount) * Decimal(str(t.percentage)) / Decimal("100")
        floor = int(exact.to_integral_value(rounding=ROUND_DOWN))
        assert s in (floor, floor + 1), (
            f"target={t.label} pct={t.percentage} amount={amount} "
            f"exact={exact} floor={floor} got={s}"
        )
