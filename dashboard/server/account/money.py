"""Turning Schwab's dollar amounts into integer cents."""

from decimal import ROUND_HALF_UP, Decimal


def cents(dollars: float | int | str | None) -> int:
    """$12.345 -> 1235. Goes through Decimal(str(x)) so 0.1 + 0.2 style float noise can't creep in."""
    if dollars is None:
        return 0
    return int((Decimal(str(dollars)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def mask(account_number: str | int) -> str:
    """The last four digits only, e.g. "…1234". Use this the moment a number is read."""
    return "…" + str(account_number)[-4:]
