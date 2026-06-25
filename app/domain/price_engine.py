from dataclasses import dataclass


@dataclass
class Tuning:
    beta: float
    depth: float
    mu: float
    net_flow_decay: float
    gamma: float
    sigma: float


@dataclass
class PriceResult:
    price: float
    band_floor_pct: float
    band_ceiling_pct: float
    net_flow: float


def next_price(*, price, quarter_open, band_floor_pct, band_ceiling_pct,
               net_flow, total_supply_held, s0, nominal_supply, floor, ceiling,
               signed_shares, event_drift, event_pct, tuning, noise) -> PriceResult:
    net_flow = net_flow * tuning.net_flow_decay + signed_shares

    impact = tuning.beta * signed_shares / tuning.depth
    momentum = tuning.mu * net_flow
    supply_pressure = -tuning.gamma * (total_supply_held - s0) / nominal_supply

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
                       band_ceiling_pct=band_ceiling_pct, net_flow=net_flow)
