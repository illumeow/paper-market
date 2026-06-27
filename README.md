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

## Local Docker test
The app serves the API + frontend directly on port 26223 (no proxy, plain HTTP).

1. `.env` — `STAFF_PASSWORD` + a random `SECRET_KEY` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. Provision the DB (writes to the mounted `./data` volume): `docker compose run --rm app python scripts/setup_db.py --reset --force`.
3. `docker compose build && docker compose up`.
4. Open `http://localhost:26223/` (redirects to the dashboard) or `http://localhost:26223/member.html` / `/teller.html`. From another LAN device use `http://<machine-ip>:26223/…`. Staff-login on `/teller.html` and click **Start event** to unfreeze the market.

## Deploy (VM)
1. Generate PINs once: `python scripts/gen_pins.py` → `config/pins.csv` (keep private).
2. Copy repo + `config/pins.csv` to the VM.
3. Create `.env` with `STAFF_PASSWORD` and a random `SECRET_KEY` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
4. Build the image: `docker compose build`.
5. **Provision the DB once** (the app no longer seeds on boot): `docker compose run --rm app python scripts/setup_db.py --reset --force`. This writes to the mounted `./data` volume.
6. Start the stack: `docker compose up -d`. The app serves both the API and the static frontend on port 26223 — plain HTTP, no reverse proxy, no TLS.
7. Print `config/pins.csv` as member cards and announce PINs.
8. **At kickoff:** open `http://<vm-ip>:26223/teller.html` and click **Start event** — this starts the clock; the market unfreezes and trading opens. (A crash/restart resumes from this start time; it never resets.)

> No HTTPS by design: this is a short, trusted, single-event LAN/VM deployment. The session cookie is `httponly`+`samesite=lax` but not `secure`. If you ever need TLS, put a reverse proxy (Caddy/nginx) in front of the app container.
