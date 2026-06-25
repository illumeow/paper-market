import pytest, app.db as db
from app import repo, services


def _m(bal=5000):
    conn = db.connect(":memory:"); db.init_schema(conn)
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at) VALUES('0-1','h',?,0.0)", (bal,))
    from app.clock import set_event_start; set_event_start(conn, 0.0)
    conn.commit(); return conn


RATES = dict(demand_rate=0.005, fd_rate_30=0.01, fd_rate_60=0.02, event_duration_min=120)


def test_open_deducts_principal():
    conn = _m()
    fd = services.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    assert repo.get_member(conn, "0-1")["balance"] == 4000
    assert len(repo.open_fds(conn, "0-1")) == 1


def test_open_blocked_past_cutoff():
    conn = _m()
    # at t=100min, 30-min term ends at 130 > 120 -> blocked
    with pytest.raises(ValueError):
        services.fd_open(conn, "0-1", 1000, 30, now=100 * 60, actor="teller", **RATES)


def test_close_matured_pays_contract_rate():
    conn = _m()
    fd = services.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    services.fd_close(conn, "0-1", fd, now=30 * 60, actor="teller", demand_rate=0.005)
    # leftover 4000 accrues at 0.5%/min: 4000*1.005^30 ≈ 4646; matured 1000*1.01^30 ≈ 1348
    assert repo.get_member(conn, "0-1")["balance"] == 5994


def test_close_early_uses_penalty_rate():
    conn = _m()
    fd = services.fd_open(conn, "0-1", 1000, 30, now=0.0, actor="teller", **RATES)
    services.fd_close(conn, "0-1", fd, now=10 * 60, actor="teller", demand_rate=0.005)
    # leftover 4000 accrues at 0.5%/min: 4000*1.005^10 ≈ 4205; early exit 1000*1.004^10 ≈ 1041
    assert repo.get_member(conn, "0-1")["balance"] == 5246
