from app.stock.engine import next_price, Tuning

T = Tuning(impact_strength=0.5, impact_depth=500, momentum_strength=0.0, momentum_decay=1.0, reversion_strength=0.0, noise_scale=0.0)


def _call(**kw):
    base = dict(price=100.0, quarter_open=100.0, band_floor_pct=-0.30, band_ceiling_pct=0.30,
                flow_momentum=0.0, total_market_shares=3000, market_share_baseline=3000,
                pressure_normalizer=10000,
                floor=30.0, ceiling=300.0, trade_shares=0, event_drift=0.0,
                event_pct=0.0, tuning=T, noise=0.0)
    base.update(kw)
    return next_price(**base)


def test_buy_pushes_price_up():
    r = _call(trade_shares=100)          # impact = 0.5*100/500 = 0.10
    assert abs(r.price - 110.0) < 1e-6
    assert r.flow_momentum == 100


def test_organic_clamped_to_quarter_band():
    r = _call(trade_shares=5000)         # impact huge -> clamp to +30% = 130
    assert abs(r.price - 130.0) < 1e-6
    assert r.band_ceiling_pct == 0.30     # organic move does not ratchet band


def test_absolute_ceiling_always_applies():
    r = _call(price=295.0, trade_shares=200, band_ceiling_pct=5.0)  # band loose, abs caps
    assert r.price <= 300.0


def test_event_bypasses_band_and_ratchets():
    # organic clamps to ceiling 130; event drift lifts to ~135; event_pct 0.10
    r = _call(price=130.0, trade_shares=0, event_drift=0.0385, event_pct=0.10)
    assert abs(r.price - 135.0) < 0.2
    # new ceiling pct = (135/100 - 1) + 0.10 = 0.45
    assert abs(r.band_ceiling_pct - 0.45) < 0.01


def test_supply_pressure_pushes_down_when_oversupplied():
    t = Tuning(impact_strength=0, impact_depth=500, momentum_strength=0, momentum_decay=1.0, reversion_strength=0.02, noise_scale=0)
    r = _call(total_market_shares=8000, tuning=t)   # -0.02*(8000-3000)/10000 = -0.01
    assert r.price < 100.0
