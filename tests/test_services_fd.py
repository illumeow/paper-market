import pytest
import app.core.db as db
from app.bank import repo as bank_repo
from app.bank import service as bank_service
from app.core.money import compound


def _m(bal=5000):
    conn = db.connect(":memory:"); db.init_schema(conn)
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at) VALUES('0-1','h',?,0.0)", (bal,))
    from app.core.clock import set_event_start; set_event_start(conn, 0.0)
    conn.commit(); return conn


RATES = dict(fd_rate_30=0.01, fd_rate_60=0.02, event_duration_min=120)


def test_open_deducts_principal():
    conn = _m()
    fd = bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    assert bank_repo.get_member(conn, "0-1")["balance"] == 4000
    assert len(bank_repo.open_fds(conn, "0-1")) == 1


def test_open_blocked_past_cutoff():
    conn = _m()
    # at t=100min, 30-min term ends at 130 > 120 -> blocked
    with pytest.raises(ValueError):
        bank_service.fd_open(conn, "0-1", 1000, 30, now=100 * 60, actor="teller", **RATES)


def test_close_matured_pays_contract_rate():
    conn = _m()
    fd = bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    bank_service.fd_close(conn, "0-1", fd, now=30 * 60, actor="teller", demand_rate=0.005)
    # leftover 4000 accrues at 0.5%/min: compound(4000, 0.005, 30)
    # matured 1000*1.01^30: compound(1000, 0.01, 30) — no rounding on either
    expected = float(compound(4000, 0.005, 30)) + float(compound(1000, 0.01, 30))
    assert bank_repo.get_member(conn, "0-1")["balance"] == pytest.approx(expected, rel=1e-9)


def test_close_early_uses_penalty_rate():
    conn = _m()
    fd = bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    bank_service.fd_close(conn, "0-1", fd, now=10 * 60, actor="teller", demand_rate=0.005)
    # leftover 4000 accrues at 0.5%/min: compound(4000, 0.005, 10)
    # early exit: compound(1000, 0.8*0.005, 10) = compound(1000, 0.004, 10) — no rounding
    expected = float(compound(4000, 0.005, 10)) + float(compound(1000, 0.004, 10))
    assert bank_repo.get_member(conn, "0-1")["balance"] == pytest.approx(expected, rel=1e-9)


def test_second_open_blocked_one_per_member():
    conn = _m()
    bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    with pytest.raises(ValueError):  # one FD per member
        bank_service.fd_open(conn, "0-1", 500, 60, now=0.0, actor="teller", **RATES)


def test_close_current_closes_member_fd_no_id():
    conn = _m()
    bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    bank_service.fd_close_current(conn, "0-1", now=30 * 60, actor="member", demand_rate=0.005)
    assert len(bank_repo.open_fds(conn, "0-1")) == 0
    with pytest.raises(ValueError):  # nothing left to close
        bank_service.fd_close_current(conn, "0-1", now=30 * 60, actor="member", demand_rate=0.005)


def test_sweep_closes_only_matured():
    conn = _m()
    bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    assert bank_service.close_matured_fds(conn, now=20 * 60, demand_rate=0.005) == 0
    assert len(bank_repo.open_fds(conn, "0-1")) == 1
    assert bank_service.close_matured_fds(conn, now=30 * 60, demand_rate=0.005) == 1
    assert len(bank_repo.open_fds(conn, "0-1")) == 0
    # matured payout landed in the balance: leftover 4000 (0.5%/30) + 1000*1.01^30
    expected = float(compound(4000, 0.005, 30)) + float(compound(1000, 0.01, 30))
    assert bank_repo.get_member(conn, "0-1")["balance"] == pytest.approx(expected, rel=1e-9)


def test_fd_public_view_shape():
    conn = _m()
    bank_service.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    fd = bank_repo.open_fds(conn, "0-1")[0]
    v = bank_service.fd_public(conn, fd, now=10 * 60, demand_rate=0.005)
    assert v["remaining_min"] == pytest.approx(20.0)
    assert v["matured"] is False
    assert v["payout"] == pytest.approx(float(compound(1000, 0.01, 30)), rel=1e-9)
    # close-now (early, penalty rate 0.8*0.005=0.004 over 10 elapsed min)
    assert v["close_value_now"] == pytest.approx(float(compound(1000, 0.004, 10)), rel=1e-9)
    assert "fd_id" not in v  # FD is bound to the member; the id is not exposed
