from decimal import Decimal, getcontext

getcontext().prec = 28


def compound(principal, rate_per_min, minutes) -> Decimal:
    """principal * (1 + rate_per_min) ** minutes, as Decimal (fractional minutes OK)."""
    base = Decimal(1) + Decimal(str(rate_per_min))
    return Decimal(str(principal)) * (base ** Decimal(str(minutes)))
