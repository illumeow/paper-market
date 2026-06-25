from decimal import Decimal, ROUND_HALF_UP
from app.domain.interest import fd_maturity, loan_owed


def member_amount(*, balance, open_fds, holdings, prices, debt, loan_elapsed_min) -> int:
    total = Decimal(balance)
    for fd in open_fds:
        total += fd_maturity(fd["principal"], fd["term_minutes"], fd["rate_per_min"])
    for h in holdings:
        total += Decimal(str(prices[h["stock_id"]])) * Decimal(h["shares"])
    if debt > 0:
        total -= loan_owed(debt, loan_elapsed_min)
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
