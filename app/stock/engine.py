from dataclasses import dataclass


@dataclass
class Tuning:
    impact_strength: float
    impact_depth: float
    momentum_strength: float
    momentum_decay: float
    reversion_strength: float
    noise_scale: float


@dataclass
class PriceResult:
    price: float
    band_floor_pct: float
    band_ceiling_pct: float
    flow_momentum: float


def next_price(*, price, quarter_open, band_floor_pct, band_ceiling_pct,
               flow_momentum, total_market_shares, market_share_baseline,
               pressure_normalizer, floor, ceiling,
               trade_shares, event_drift, event_pct, tuning, noise) -> PriceResult:
    flow_momentum = flow_momentum * tuning.momentum_decay + trade_shares

    impact = tuning.impact_strength * trade_shares / tuning.impact_depth
    momentum = tuning.momentum_strength * flow_momentum
    supply_pressure = -tuning.reversion_strength * (total_market_shares - market_share_baseline) / pressure_normalizer

    # 1) organic move (no event), clamped to current quarter band
    organic = price * (1 + impact + momentum + supply_pressure + noise)
    lo = quarter_open * (1 + band_floor_pct)
    hi = quarter_open * (1 + band_ceiling_pct)
    organic = max(lo, min(hi, organic))

    # 2) event drift bypasses the band
    final = organic * (1 + event_drift)

    # 3) ratchet band if event pushed past a boundary: new bound = price pct + event size
    final_pct = final / quarter_open - 1
    epsilon = 1e-9
    if final_pct > band_ceiling_pct + epsilon:
        band_ceiling_pct = final_pct + abs(event_pct)
    elif final_pct < band_floor_pct - epsilon:
        band_floor_pct = final_pct - abs(event_pct)

    # 4) absolute bounds always
    final = max(floor, min(ceiling, final))

    return PriceResult(price=final, band_floor_pct=band_floor_pct,
                       band_ceiling_pct=band_ceiling_pct, flow_momentum=flow_momentum)
