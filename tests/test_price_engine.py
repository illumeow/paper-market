from app.domain.price_engine import next_price, Tuning

T = Tuning(beta=0.5, depth=500, mu=0.0, net_flow_decay=1.0, gamma=0.0, sigma=0.0)


def _call(**kw):
    base = dict(price=100.0, quarter_open=100.0, band_floor_pct=-0.30, band_ceiling_pct=0.30,
                net_flow=0.0, total_supply_held=3000, s0=3000, nominal_supply=10000,
                floor=30.0, ceiling=300.0, signed_shares=0, event_drift=0.0,
                event_pct=0.0, tuning=T, noise=0.0)
    base.update(kw)
    return next_price(**base)


def test_buy_pushes_price_up():
    r = _call(signed_shares=100)          # impact = 0.5*100/500 = 0.10
    assert abs(r.price - 110.0) < 1e-6
    assert r.net_flow == 100


def test_organic_clamped_to_quarter_band():
    r = _call(signed_shares=5000)         # impact huge -> clamp to +30% = 130
    assert abs(r.price - 130.0) < 1e-6
    assert r.band_ceiling_pct == 0.30     # organic move does not ratchet band


def test_absolute_ceiling_always_applies():
    r = _call(price=295.0, signed_shares=200, band_ceiling_pct=5.0)  # band loose, abs caps
    assert r.price <= 300.0


def test_event_bypasses_band_and_ratchets():
    # organic clamps to ceiling 130; event drift lifts to ~135; event_pct 0.10
    r = _call(price=130.0, signed_shares=0, event_drift=0.0385, event_pct=0.10)
    assert abs(r.price - 135.0) < 0.2
    # new ceiling pct = (135/100 - 1) + 0.10 = 0.45
    assert abs(r.band_ceiling_pct - 0.45) < 0.01


def test_supply_pressure_pushes_down_when_oversupplied():
    t = Tuning(beta=0, depth=500, mu=0, net_flow_decay=1.0, gamma=0.02, sigma=0)
    r = _call(total_supply_held=8000, tuning=t)   # -0.02*(8000-3000)/10000 = -0.01
    assert r.price < 100.0
