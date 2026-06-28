from app.core.networth import member_networth


def test_amount_combines_all_parts():
    amt = member_networth(
        balance=1000,
        # open FD valued at its FD-rate accrual to now: 1000*1.01^10 ≈ 1104.62
        open_fds=[{"principal": 1000, "term_minutes": 30, "rate_per_min": 0.01, "elapsed_min": 10}],
        holdings=[{"stock_id": "TECH", "shares": 10}],
        prices={"TECH": 120.0},                                                     # ->1200
        debt=500, loan_elapsed_min=10,                                              # 500*1.03^10≈671.96
    )
    # 1000 + 1104.62 + 1200 - 671.96 ≈ 2632.66 -> 2633 (rounded)
    assert amt == 2633


def test_open_fd_accrual_caps_at_term():
    # elapsed past term must not over-accrue: caps at the full-term value.
    amt = member_networth(
        balance=0,
        open_fds=[{"principal": 1000, "term_minutes": 30, "rate_per_min": 0.01, "elapsed_min": 100}],
        holdings=[], prices={}, debt=0, loan_elapsed_min=0,
    )
    assert amt == 1348  # 1000*1.01^30 ≈ 1347.85


def test_no_debt_no_fd():
    assert member_networth(balance=500, open_fds=[], holdings=[], prices={},
                         debt=0, loan_elapsed_min=0) == 500
