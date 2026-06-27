# Deploying paper-market

A single-VM, single-event deployment. One Docker container serves the API **and** the static frontend over plain HTTP on port 26223 — no reverse proxy, no TLS. This is intentional: the event is short, on a trusted network, behind a known IP. (If you ever need HTTPS, put Caddy/nginx in front of the container; nothing else changes.)

## What you need

- A VM with **Docker** + **docker compose** installed.
- Inbound **TCP port 26223** open to the devices that will use it (cloud security group / firewall).
- Python 3.11 **once, on any machine**, to generate the PIN list.
- The members and staff all reachable on the same LAN as the VM (or the VM publicly reachable by IP).

## One-time prep (before the event)

### 1. Generate the PIN list (local, once)
```bash
python scripts/gen_pins.py        # writes config/pins.csv — 120 unique 4-digit PINs
```
`config/pins.csv` is the **master credential list**. It is gitignored on purpose — never commit it, keep it private, and move it to the VM out-of-band (step 3).

### 2. Get the code onto the VM
```bash
git clone <repo-url> paper-market
cd paper-market
```

### 3. Copy the PIN list to the VM (separately)
`config/pins.csv` is not in git, so copy it by hand:
```bash
scp config/pins.csv  user@<vm>:~/paper-market/config/pins.csv
```

### 4. Create `.env` on the VM
```bash
cat > .env <<EOF
STAFF_PASSWORD=<pick a staff password>
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
EOF
```
- `SECRET_KEY` signs the session cookie — must be a strong random value, unique per deployment. Regenerating it logs everyone out.
- `STAFF_PASSWORD` is the single password staff type to log into the Teller Panel.

### 5. Build the image
```bash
docker compose build
```

### 6. Provision the database (once)
The app does **not** seed on boot — it only resumes. Provision the DB explicitly:
```bash
docker compose run --rm app python scripts/setup_db.py --reset --force
```
This creates members (from `config/pins.csv`), stocks + events (from `config/config.toml`) in `./data/paper.db` (a mounted volume on the host). `--reset` wipes any existing data; drop it to provision only if empty.

`setup_db.py` does **not** start the event clock — that's a deliberate staff action at kickoff (step 9).

### 7. Start the stack
```bash
docker compose up -d
```
The app now serves on port 26223.

### 8. Verify it's up
```bash
docker compose ps               # app should be "running", "0.0.0.0:26223->8000"
docker compose logs app         # no errors; should not say "not provisioned"
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:26223/dashboard.html   # 200
```
From another device on the LAN: open `http://<vm-ip>:26223/` (it redirects to the dashboard).
Find the VM's IP with `ip addr` / `hostname -I` (Linux) or your cloud console.

### 9. Hand out PINs
Print `config/pins.csv` as member cards (member id + PIN) and distribute. Tell staff the `STAFF_PASSWORD`.

## At kickoff

The market is **frozen** and trading is **blocked (409)** until you start the event. Banking (deposit/withdraw/loan/relief/FD) is allowed before kickoff; interest only starts accruing from kickoff.

1. Open `http://<vm-ip>:26223/teller.html`, log in with the staff password.
2. Click **Start event**.

This sets the event clock once. Scheduled price events (`at_min` in `config.toml`) and all interest accrual are measured from that moment. The start time persists in the DB — a crash/restart **resumes** from it and never resets.

## During / after the event

**URLs** (replace `<vm-ip>`; works by IP over HTTP, no domain needed):
- Members: `http://<vm-ip>:26223/member.html`
- Staff teller: `http://<vm-ip>:26223/teller.html`
- Public dashboard (prices, news, leaderboard feed): `http://<vm-ip>:26223/dashboard.html`
- Bare `http://<vm-ip>:26223/` redirects to the dashboard.

**Export final results** (CSV of every member's net worth): logged in as staff in the browser, open `http://<vm-ip>:26223/api/export` — it downloads `paper-market.csv`.

**Restart / crash recovery:** `docker compose up -d` (or the VM rebooting) resumes the existing DB and event clock. It never reseeds or resets the clock.

**Reset for a fresh run / rehearsal:**
```bash
docker compose down
docker compose run --rm app python scripts/setup_db.py --reset --force
docker compose up -d
```
This wipes all balances/trades and unsets the clock (you start the event again from the Teller Panel).

**Back up the live DB** (e.g. mid-event safety copy):
```bash
cp data/paper.db data/paper.db.bak     # include -wal/-shm if present
```

**Logs / stop:**
```bash
docker compose logs -f app
docker compose down                    # stop (data persists in ./data)
```

## Editing config

`./config` is mounted read-only into the container, so you can edit `config/config.toml` (stocks, economy rates, scheduled events) on the host. Changes that affect already-provisioned rows (members/stocks/events) only take effect on the next `setup_db.py --reset`. Tuning/tick values are read at startup — `docker compose restart app` to apply.

## Redeploying after a change

Application code (`app/`, `frontend/`, `scripts/`, `pyproject.toml`) is **copied into the image at build time** — only `./data` and `./config` are mounted. So a plain `docker compose up -d` reuses the old image and your code change won't appear.

| Changed | What to run |
|---|---|
| `app/**`, `frontend/**`, `scripts/**`, `pyproject.toml` | `docker compose up -d --build` |
| `.env` | `docker compose up -d` (recreates the container, re-reads env) |
| `config/config.toml` only | `docker compose restart app` |

`docker compose up -d --build` is a safe default for almost everything — the build cache makes it near-instant when nothing changed, and it never touches `./data` (DB + event clock persist). **One exception:** a `config/config.toml`-only edit leaves the image and container spec unchanged, so compose reports "up to date" and does **not** recreate — the new config is never re-read. Use `docker compose restart app` for that case.

The prod `CMD` has no `--reload`, so nothing hot-reloads — every change needs a rebuild or restart as above.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `http://localhost:26223/` refused | Port 26223 already in use, or container not up. `docker compose ps` / `logs app`. Remap host port in `docker-compose.yml` (`"8080:8000"`) → use `http://localhost:8080/`. |
| Boot error "DB ... is not provisioned (0 members)" | You skipped step 6. Run `docker compose run --rm app python scripts/setup_db.py --reset --force`. |
| Trades return **409 "event not started"** | Expected before kickoff. Staff → **Start event** on the Teller Panel. |
| Can't reach from another device | Firewall/security group not allowing inbound TCP 26223; or devices on a different subnet / guest Wi-Fi with AP isolation. |
| `setup_db.py` can't find PINs | `config/pins.csv` missing on the VM — copy it (step 3). |
| Everyone logged out after redeploy | `SECRET_KEY` changed. Keep it stable across restarts. |

## Security notes

- `config/pins.csv` is the master credential list — keep it private, never commit it.
- `SECRET_KEY` must be strong, random, and unique to this deployment (cookie signing → auth bypass if guessable).
- Plain HTTP is acceptable only for this short, trusted, single-event setup; the session cookie is `httponly`+`samesite=lax` but **not** `secure`. Don't expose this to the open internet without TLS.
