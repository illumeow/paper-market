from decimal import Decimal
from app.bank.interest import fd_maturity, loan_owed
from app.core.money import _int


def member_amount(*, balance, open_fds, holdings, prices, debt, loan_elapsed_min) -> int:
    # The ONE place money rounds to whole units: the export/scoreboard boundary.
    # Cash, debt, FD payouts and positions are all carried full-precision until here.
    total = Decimal(str(balance))
    for fd in open_fds:
        total += fd_maturity(fd["principal"], fd["term_minutes"], fd["rate_per_min"])
    for h in holdings:
        total += Decimal(str(prices[h["stock_id"]])) * Decimal(h["shares"])
    if debt > 0:
        total -= loan_owed(debt, loan_elapsed_min)
    return _int(total)
