from decimal import Decimal
from app.core.money import compound
from app.bank import interest


def test_compound_basic():
    assert compound(1000, 0.005, 0) == Decimal(1000)
    got = compound(1000, 0.005, 10)            # 1000 * 1.005^10
    assert abs(got - Decimal("1051.14")) < Decimal("0.01")


def test_demand_balance_fractional_minutes():
    got = interest.demand_balance(1000, 30.0)  # 1.005^30 ≈ 1.1614
    assert abs(got - Decimal("1161.40")) < Decimal("0.05")


def test_fd_maturity_30_and_60():
    assert abs(interest.fd_maturity(1000, 30, 0.01) - Decimal("1347.85")) < Decimal("0.1")
    assert abs(interest.fd_maturity(1000, 60, 0.02) - Decimal("3281.03")) < Decimal("0.5")


def test_fd_early_exit_uses_penalty_rate():
    # rate = 0.8 * 0.005 = 0.004 ; 10 min
    assert abs(interest.fd_early_exit(1000, 10) - Decimal("1040.71")) < Decimal("0.05")


def test_loan_owed():
    assert abs(interest.loan_owed(5000, 20, 0.03) - Decimal("9030.56")) < Decimal("1")
