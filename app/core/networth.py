from decimal import Decimal
from app.bank.interest import fd_accrued, loan_owed
from app.core.money import _int


def member_amount(*, balance, open_fds, holdings, prices, debt, loan_elapsed_min) -> int:
    # The ONE place money rounds to whole units: the export/scoreboard boundary.
    # Cash, debt, FD value and positions are all carried full-precision until here.
    total = Decimal(str(balance))
    for fd in open_fds:
        # A still-open FD counts at its FD-rate value accrued to now (capped at
        # term), not the full maturity payout. FDs are expected closed before
        # export; this is the safety net for any left open.
        total += fd_accrued(fd["principal"], fd["elapsed_min"], fd["rate_per_min"], fd["term_minutes"])
    for h in holdings:
        total += Decimal(str(prices[h["stock_id"]])) * Decimal(h["shares"])
    if debt > 0:
        total -= loan_owed(debt, loan_elapsed_min)
    return _int(total)
