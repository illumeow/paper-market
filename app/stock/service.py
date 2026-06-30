import random as _random
from decimal import Decimal
from app.bank.service import accrue_balance
from app.bank.repo import update_member
from app.stock import repo
from app.stock.engine import next_price
from app.core.errors import BusinessError


def execute_trade(conn, mid, sid, side, shares, now, actor, *, tuning, noise_scale, rng=_random):
    if shares <= 0 or side not in ("buy", "sell"):
        raise BusinessError("Invalid trade")
    s = repo.get_stock(conn, sid)
    if s is None:
        raise BusinessError("Unknown stock")
    price = s["price"]
    cost = float(Decimal(str(price)) * shares)
    bal = accrue_balance(conn, mid, now)
    held = repo.get_holding(conn, mid, sid)

    if side == "buy":
        if cost > bal:
            raise BusinessError("Insufficient balance")
        update_member(conn, mid, balance=bal - cost)
        repo.set_holding(conn, mid, sid, held + shares)
        signed = shares
    else:
        if shares > held:
            raise BusinessError("Insufficient shares")
        update_member(conn, mid, balance=bal + cost)
        repo.set_holding(conn, mid, sid, held - shares)
        signed = -shares

    noise = rng.uniform(-noise_scale, noise_scale)
    r = next_price(price=price, quarter_open=s["quarter_open_price"],
                   band_floor_pct=s["band_floor_pct"], band_ceiling_pct=s["band_ceiling_pct"],
                   flow_momentum=s["flow_momentum"], total_market_shares=s["total_market_shares"],
                   market_share_baseline=s["market_share_baseline"],
                   pressure_normalizer=s["pressure_normalizer"], floor=s["floor"],
                   ceiling=s["ceiling"], trade_shares=signed, event_drift=0.0,
                   event_pct=0.0, tuning=tuning, noise=noise)
    repo.update_stock(conn, sid, price=r.price, band_floor_pct=r.band_floor_pct,
                      band_ceiling_pct=r.band_ceiling_pct, flow_momentum=r.flow_momentum,
                      total_market_shares=s["total_market_shares"] + signed,
                      trade_count=s["trade_count"] + 1)
    conn.execute("INSERT INTO price_history(stock_id,ts,price) VALUES(?,?,?)", (sid, now, r.price))
    repo.add_trade(conn, mid, sid, side, shares, price, now, actor)
    conn.commit()
    return {"price": r.price, "shares": shares}
