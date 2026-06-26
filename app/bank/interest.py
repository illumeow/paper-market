from decimal import Decimal
from app.core.money import compound


def demand_balance(principal, minutes, demand_rate=0.005) -> Decimal:
    return compound(principal, demand_rate, minutes)


def fd_maturity(principal, term_minutes, rate_per_min) -> Decimal:
    return compound(principal, rate_per_min, term_minutes)


def fd_early_exit(principal, elapsed_minutes, demand_rate=0.005) -> Decimal:
    return compound(principal, 0.8 * demand_rate, elapsed_minutes)


def loan_owed(debt, elapsed_minutes, loan_rate=0.03) -> Decimal:
    return compound(debt, loan_rate, elapsed_minutes)
