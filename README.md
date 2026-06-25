# paper-market

Fake-money banking + stock-trading simulation for a camp casino event (FastAPI + SQLite, Caddy auto-HTTPS).

## Local dev
pip install -e ".[dev]"
uvicorn app.main:app --reload
# open http://localhost:8000/member.html etc.

## Deploy (VM)
1. Generate PINs once: `python scripts/gen_pins.py` -> config/pins.csv (keep private)
2. Copy repo + config/pins.csv to the VM.
3. Point DNS A record for $DOMAIN at the VM.
4. Create .env with DOMAIN, STAFF_PASSWORD, SECRET_KEY.
5. `docker compose up -d --build`
6. Print config/pins.csv as member cards.
