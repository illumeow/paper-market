from decimal import Decimal
from app.core.money import compound


def demand_balance(principal, minutes, demand_rate=0.005) -> Decimal:
    return compound(principal, demand_rate, minutes)


def fd_maturity(principal, term_minutes, rate_per_min) -> Decimal:
    return compound(principal, rate_per_min, term_minutes)


def fd_early_exit(principal, elapsed_minutes, demand_rate=0.005) -> Decimal:
    return compound(principal, 0.8 * demand_rate, elapsed_minutes)


def fd_accrued(principal, elapsed_minutes, rate_per_min, term_minutes) -> Decimal:
    """FD value accrued at its own rate up to now, capped at the term — the
    scoreboard worth of a still-open FD at export. Distinct from fd_early_exit
    (the penalty rate a member gets for closing early) and fd_maturity (the full
    term payout): this is the as-of-now value if it kept its FD rate."""
    return compound(principal, rate_per_min, min(elapsed_minutes, term_minutes))


def loan_owed(debt, elapsed_minutes, loan_rate=0.03) -> Decimal:
    return compound(debt, loan_rate, elapsed_minutes)
