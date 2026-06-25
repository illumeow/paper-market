from app.domain.networth import member_amount


def test_amount_combines_all_parts():
    amt = member_amount(
        balance=1000,
        open_fds=[{"principal": 1000, "term_minutes": 30, "rate_per_min": 0.01}],  # ->1347.85
        holdings=[{"stock_id": "TECH", "shares": 10}],
        prices={"TECH": 120.0},                                                     # ->1200
        debt=500, loan_elapsed_min=10,                                              # 500*1.03^10≈671.96
    )
    # 1000 + 1348 + 1200 - 672 ≈ 2876 (rounded)
    assert amt == 2876


def test_no_debt_no_fd():
    assert member_amount(balance=500, open_fds=[], holdings=[], prices={},
                         debt=0, loan_elapsed_min=0) == 500
