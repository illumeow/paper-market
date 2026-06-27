import { api, stream, money, count } from "/js/common.js";

// ── Toast helper ────────────────────────────────────────
const toastEl = document.getElementById("toast");
let toastTimer;
function toast(msg, type = "ok") {
  clearTimeout(toastTimer);
  toastEl.textContent = msg;
  toastEl.className = `show toast-${type}`;
  toastTimer = setTimeout(() => { toastEl.className = ""; }, 3200);
}

// ── State ───────────────────────────────────────────────
let prices = {}; // stock_id -> current price (live)

// ── DOM refs ────────────────────────────────────────────
const loginSection = document.getElementById("login-section");
const appSection   = document.getElementById("app-section");
const pinInput     = document.getElementById("pin-input");
const loginBtn     = document.getElementById("login-btn");
const midLabel     = document.getElementById("member-id-label");
const statBalance  = document.getElementById("stat-balance");
const statDebt     = document.getElementById("stat-debt");
const holdingsList = document.getElementById("holdings-list");
const fdList       = document.getElementById("fd-list");
const marketList   = document.getElementById("market-list");

// ── Formatting ──────────────────────────────────────────
function fmtRate(r) { return (r * 100).toFixed(3) + "%/min"; }

// ── Render portfolio ────────────────────────────────────
function renderPortfolio(me) {
  midLabel.textContent = me.member_id;
  statBalance.textContent = "$" + money(me.balance);
  statDebt.textContent = me.debt > 0 ? "$" + money(me.debt) : "—";

  // holdings
  if (me.holdings && me.holdings.length > 0) {
    holdingsList.innerHTML = me.holdings.map(h =>
      `<div class="row row--between" style="padding:4px 0;border-bottom:1px solid var(--border)">
        <span class="stock-name">${h.stock_id}</span>
        <span>${count(h.shares)} shares</span>
      </div>`
    ).join("");
  } else {
    holdingsList.innerHTML = '<span class="muted">No shares held.</span>';
  }

  // FDs
  if (me.fixed_deposits && me.fixed_deposits.length > 0) {
    holdingsList.parentElement; // already set above
    const rows = me.fixed_deposits.map(f =>
      `<tr>
        <td>${f.fd_id}</td>
        <td>$${money(f.principal)}</td>
        <td>${f.term_minutes}min</td>
        <td>${fmtRate(f.rate_per_min)}</td>
      </tr>`
    ).join("");
    fdList.innerHTML = `<table class="fd-table">
      <thead><tr><th>ID</th><th>Principal</th><th>Term</th><th>Rate</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  } else {
    fdList.innerHTML = '<span class="muted">No open FDs.</span>';
  }
}

// ── Render market list ──────────────────────────────────
function renderMarket(market) {
  marketList.innerHTML = "";
  for (const s of market) {
    prices[s.stock_id] = s.price;
    const div = document.createElement("div");
    div.className = "stock-row";
    div.id = "stock-" + s.stock_id;
    div.innerHTML = `
      <div class="row row--between">
        <span class="stock-name">${s.name} <span class="muted">(${s.stock_id})</span></span>
        <span class="stock-price" id="price-${s.stock_id}">$${money(s.price)}</span>
      </div>
      <div class="trade-controls">
        <input type="number" min="1" value="1" id="shares-${s.stock_id}" placeholder="qty" />
        <button class="btn btn--success btn--sm" data-sid="${s.stock_id}" data-side="buy">Buy</button>
        <button class="btn btn--danger btn--sm"  data-sid="${s.stock_id}" data-side="sell">Sell</button>
      </div>`;
    marketList.appendChild(div);
  }

  // Trade buttons
  marketList.addEventListener("click", async e => {
    const btn = e.target.closest("[data-side]");
    if (!btn) return;
    const sid   = btn.dataset.sid;
    const side  = btn.dataset.side;
    const qtyEl = document.getElementById("shares-" + sid);
    const shares = parseInt(qtyEl.value, 10);
    if (!shares || shares < 1) { toast("Enter a valid quantity", "err"); return; }
    btn.disabled = true;
    try {
      const res = await api("/api/trade", "POST", { stock_id: sid, side, shares });
      toast(`${side === "buy" ? "Bought" : "Sold"} ${res.shares} shares @ $${money(res.price)}`, "ok");
      await refreshMe();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
    }
  });
}

// ── Live price updates ──────────────────────────────────
function onPrices(updates) {
  for (const u of updates) {
    prices[u.stock_id] = u.price;
    const el = document.getElementById("price-" + u.stock_id);
    if (el) el.textContent = "$" + money(u.price);
  }
  refreshMe();
}
function onNews(n) {
  toast(n.text, "ok");
}

// ── Refresh me ──────────────────────────────────────────
async function refreshMe() {
  try {
    const me = await api("/api/me");
    renderPortfolio(me);
  } catch (_) { /* silently ignore if session expired */ }
}

// ── Init ────────────────────────────────────────────────
async function init() {
  // Check if already logged in
  try {
    const me = await api("/api/me");
    showApp(me);
  } catch (_) {
    // Not logged in — show login form
  }
}

// ── Stream with auto-reconnect ────────────────────────────
function connectStream() {
  const es = stream(onPrices, onNews);
  es.onerror = () => {
    es.close();
    setTimeout(connectStream, 3000);
  };
}

function showApp(me) {
  loginSection.classList.add("hidden");
  appSection.classList.remove("hidden");
  renderPortfolio(me);
  // Load market
  api("/api/market").then(market => renderMarket(market)).catch(err => toast(err.message, "err"));
  // Subscribe to stream
  connectStream();
}

// ── Login ───────────────────────────────────────────────
loginBtn.addEventListener("click", async () => {
  const pin = pinInput.value.trim();
  if (pin.length !== 4 || !/^\d{4}$/.test(pin)) {
    toast("PIN must be 4 digits", "err");
    return;
  }
  loginBtn.disabled = true;
  try {
    await api("/api/login/member", "POST", { pin });
    const me = await api("/api/me");
    showApp(me);
  } catch (err) {
    toast(err.message, "err");
    pinInput.value = "";
    pinInput.focus();
  } finally {
    loginBtn.disabled = false;
  }
});

pinInput.addEventListener("keydown", e => {
  if (e.key === "Enter") loginBtn.click();
});

// ── Logout ──────────────────────────────────────────────
document.getElementById("logout-btn").addEventListener("click", async () => {
  try { await api("/api/logout", "POST"); } catch (_) { /* clear locally regardless */ }
  location.reload();  // re-runs init() → no cookie → login screen
});

init();
