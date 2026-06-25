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
