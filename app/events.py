from app import repo
from app.clock import elapsed_min, quarter_index
from app.domain.price_engine import next_price


def event_drift_for(stock_id, active_events, tick_min):
    drift, dom_pct = 0.0, 0.0
    for e in active_events:
        if e["stock_id"] in (stock_id, "all"):
            per_tick = (1 + e["pct"]) ** (tick_min / e["duration_min"]) - 1
            drift += per_tick
            if abs(e["pct"]) > abs(dom_pct):
                dom_pct = e["pct"]
    return drift, dom_pct


def tick_prices(conn, now, *, tuning, sigma, quarter_min, tick_min, rng):
    elapsed = elapsed_min(conn, now)

    # Fire due events
    for e in repo.due_events(conn, elapsed):
        repo.mark_event_fired(conn, e["id"])
        if e["headline"]:
            repo.add_news(conn, e["headline"], "event", now)

    # Quarter rollover: check if quarter index increased
    q = quarter_index(conn, quarter_min, now)
    row = conn.execute("SELECT value FROM meta WHERE key='last_quarter'").fetchone()
    last_q = int(row["value"]) if row else 0

    if q > last_q:
        for s in repo.all_stocks(conn):
            s = dict(s)
            repo.update_stock(conn, s["stock_id"],
                              quarter_open_price=s["price"],
                              band_floor_pct=-0.30,
                              band_ceiling_pct=0.30)
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('last_quarter',?)", (str(q),))

    # Compute active events AFTER potential rollover
    active = [dict(r) for r in repo.active_events(conn, elapsed)]

    updated = []
    # Re-fetch stocks AFTER rollover so we read the reset bands
    for s in repo.all_stocks(conn):
        s = dict(s)
        drift, dom_pct = event_drift_for(s["stock_id"], active, tick_min)
        noise = rng.uniform(-sigma, sigma)
        r = next_price(price=s["price"], quarter_open=s["quarter_open_price"],
                       band_floor_pct=s["band_floor_pct"], band_ceiling_pct=s["band_ceiling_pct"],
                       net_flow=s["net_flow"], total_supply_held=s["total_supply_held"],
                       s0=s["s0"], nominal_supply=s["nominal_supply"], floor=s["floor"],
                       ceiling=s["ceiling"], signed_shares=0, event_drift=drift,
                       event_pct=dom_pct, tuning=tuning, noise=noise)
        repo.update_stock(conn, s["stock_id"], price=r.price, band_floor_pct=r.band_floor_pct,
                          band_ceiling_pct=r.band_ceiling_pct, net_flow=r.net_flow)
        conn.execute("INSERT INTO price_history(stock_id,ts,price) VALUES(?,?,?)",
                     (s["stock_id"], now, r.price))
        updated.append({"stock_id": s["stock_id"], "price": r.price})

    conn.commit()
    return updated
