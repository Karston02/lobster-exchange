"""Turning dollar amounts into whole numbers of cents (or finer units), and masking account numbers."""

from decimal import ROUND_HALF_UP, Decimal


def scaled(value: float | int | str | None, decimals: int) -> int:
    """A price as a whole number of its smallest unit: scaled(12.345, 2) -> 1235,
    scaled(0.00001234, 8) -> 1234. Goes through Decimal(str(x)) so float noise can't creep in."""
    if value is None:
        return 0
    return int((Decimal(str(value)) * 10**decimals).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def cents(dollars: float | int | str | None) -> int:
    """$12.345 -> 1235."""
    return scaled(dollars, 2)


def per_unit(total_cents: int, units: float) -> int:
    """Cents per unit, rounding halves up. (Python's round() sends 292.5 to 292, the nearest even.)"""
    if not units:
        return 0
    return int((Decimal(total_cents) / Decimal(str(units))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def mask(account_number: str | int) -> str:
    """The last four digits only, e.g. "…1234". Use this the moment a number is read."""
    return "…" + str(account_number)[-4:]
