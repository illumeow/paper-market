# paper-market

Fake-money banking + stock-trading simulation for a camp casino event (FastAPI + SQLite, Caddy auto-HTTPS).

## Local dev
```
pip install -e ".[dev]"
python scripts/setup_db.py            # provision the DB (members/stocks/events). Add --reset to wipe & re-provision.
uvicorn app.main:app --reload
# open http://localhost:8000/member.html  /teller.html  /dashboard.html
```
Notes:
- The app does **not** seed on boot — it only resumes. If the DB isn't provisioned it fails at startup telling you to run `scripts/setup_db.py`. A normal restart (or accidental Ctrl-C) resumes the existing state.
- The market is **frozen** and trading is **blocked** until you explicitly start the event: log in to the Teller Panel and hit **Start event**. `at_min`/elapsed for scheduled events are measured from that moment.
- Re-test from scratch: `python scripts/setup_db.py --reset` (drops all data; the clock is unset again until the next Start).

## Local Docker test (no domain)
Caddy auto-HTTPS needs a real public domain, so for local testing serve plain HTTP instead (the session cookie is not `secure`, so HTTP is fine for testing — never for the real event).

1. `.env` — set `DOMAIN` to an HTTP address so Caddy skips TLS:
   - `DOMAIN=:80` → serves HTTP on all interfaces; reach it from other LAN devices at `http://<machine-ip>/`.
   - `DOMAIN=http://localhost` → localhost only.
   Plus `STAFF_PASSWORD` and a random `SECRET_KEY` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. Provision the DB (writes to the mounted `./data` volume): `docker compose run --rm app python scripts/setup_db.py --reset --force`.
3. `docker compose build && docker compose up`.
4. Open `http://localhost/member.html` (or `http://<machine-ip>/…`). Staff-login on `/teller.html` and click **Start event** to unfreeze the market.

Do NOT put a bare IP in `DOMAIN` expecting HTTPS — Caddy can't issue a public cert for an IP. Use `DOMAIN=:80` and HTTP.

## Deploy (VM)
1. Generate PINs once: `python scripts/gen_pins.py` → `config/pins.csv` (keep private).
2. Copy repo + `config/pins.csv` to the VM.
3. Point a DNS A record for `$DOMAIN` at the VM. (Caddy needs a real domain for auto-HTTPS; see open ports 80+443.)
4. Create `.env` with `DOMAIN`, `STAFF_PASSWORD`, `SECRET_KEY`.
5. Build the image: `docker compose build`.
6. **Provision the DB once** (the app no longer seeds on boot): `docker compose run --rm app python scripts/setup_db.py --reset --force`. This writes to the mounted `./data` volume.
7. Start the stack: `docker compose up -d`.
8. Print `config/pins.csv` as member cards and announce PINs.
9. **At kickoff:** open the Teller Panel and click **Start event** — this starts the clock; the market unfreezes and trading opens. (A crash/restart resumes from this start time; it never resets.)
