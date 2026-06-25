from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

CENT = Decimal("0.01")


def quantized_total(percentages: Iterable[object]) -> Decimal:
    """Sum percentages at the stored NUMERIC(5,2) precision, so every layer
    validates the same 2-decimal value the database keeps and payouts use."""
    return sum(
        (Decimal(str(p)).quantize(CENT, rounding=ROUND_HALF_UP) for p in percentages),
        Decimal("0"),
    )


def percentages_sum_to_100(percentages: Iterable[object]) -> bool:
    return quantized_total(percentages) == Decimal("100")
