"""Money and FX. The only place amounts change currency.

Amounts are integer minor units. Rates are decimal strings: 1 source = rate target.
Conversion rounds half-even once, at the end (policy.json states this).
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

EXPONENTS = {"KZT": 2, "USD": 2, "EUR": 2, "UZS": 2, "JPY": 0, "KWD": 3, "GBP": 2, "CNY": 2}


def exponent(ccy: str) -> int:
    try:
        return EXPONENTS[ccy]
    except KeyError as exc:
        raise ValueError(f"unknown currency {ccy}") from exc


def convert(amount_minor: int, src: str, dst: str, rate: str) -> int:
    """Convert integer minor units of ``src`` into minor units of ``dst`` at ``rate``."""
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise TypeError("amount_minor must be int")
    if src == dst:
        return amount_minor
    with localcontext() as ctx:
        ctx.prec = 40
        ctx.rounding = ROUND_HALF_EVEN
        value = Decimal(amount_minor) * Decimal(rate) * (Decimal(10) ** (exponent(dst) - exponent(src)))
        return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
