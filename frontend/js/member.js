import { api, stream, money, count, ratePct, fdPayout, fdTermSelect, fdTermRate } from "/js/common.js";

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
let heldShares = {};  // stock_id -> shares held
let marketIds = [];   // stock ids currently rendered, for held-label updates

// ── DOM refs ────────────────────────────────────────────
const loginSection = document.getElementById("login-section");
const appSection   = document.getElementById("app-section");
const pinInput     = document.getElementById("pin-input");
const loginBtn     = document.getElementById("login-btn");
const midLabel     = document.getElementById("member-id-label");
const statBalance  = document.getElementById("stat-balance");
const statDebt     = document.getElementById("stat-debt");
const fdList       = document.getElementById("fd-list");
const marketList   = document.getElementById("market-list");

// ── Render portfolio ────────────────────────────────────
function renderPortfolio(me) {
  midLabel.textContent = me.member_id;
  statBalance.textContent = "$" + money(me.balance);
  statDebt.textContent = me.debt > 0 ? "$" + money(me.debt) : "—";

  // Holdings are now shown inline per stock row (see updateHeldDisplays).
  heldShares = {};
  (me.holdings || []).forEach(h => { heldShares[h.stock_id] = h.shares; });
  updateHeldDisplays();

  renderFd(me);
}

// ── Fixed deposit: show the open FD as a card, else the open form ──
// One FD per member. fdShown tracks what's rendered so the auto-refresh tick
// (every price update) never rebuilds — and wipes — a half-typed open form.
let fdShown = null;     // 'card' | 'form'
let currentFd = null;   // the open FD (for the close confirm); null when none

function renderFd(me) {
  const fd = me.fixed_deposits && me.fixed_deposits[0];
  currentFd = fd || null;
  if (fd) {
    fdList.innerHTML = fdCardHtml(fd);   // no inputs in the card → safe to re-render each tick
    fdShown = "card";
    return;
  }
  if (fdShown !== "form") {              // only build the form on the none→form transition
    fdList.innerHTML = fdFormHtml(me);
    wireFdForm();
    fdShown = "form";
  }
}

function fdCardHtml(fd) {
  const status = fd.matured
    ? '<span class="pos">✓ Matured</span>'
    : `matures in ${Math.max(0, Math.ceil(fd.remaining_min))} min`;
  return `<table class="fd-table"><tbody>
    <tr><td>Principal</td><td>$${money(fd.principal)}</td></tr>
    <tr><td>Term</td><td>${fd.term_minutes} min · ${ratePct(fd.rate_per_min)}/min</td></tr>
    <tr><td>Matures to</td><td>$${money(fd.payout)}</td></tr>
    <tr><td>Status</td><td>${status}</td></tr>
  </tbody></table>
  <div class="fd-actions-right"><button class="btn btn--danger btn--sm" id="fd-close-btn">Close FD</button></div>`;
}

function fdFormHtml(me) {
  const opts = (me.fd_options || []).filter(o => me.elapsed_min + o.term <= me.event_duration_min);
  if (opts.length === 0) {
    return '<span class="muted">FD window closed — too close to event end.</span>';
  }
  return `<div class="fd-open-form">
    <div class="fd-open-row">
      <input type="number" min="1" id="fd-principal" placeholder="Amount" />
      ${fdTermSelect(opts)}
    </div>
    <div class="fd-open-actions">
      <span class="muted" id="fd-preview"></span>
      <button class="btn btn--primary btn--sm" id="fd-open-btn">Open FD</button>
    </div>
  </div>`;
}

function wireFdForm() {
  const principal = document.getElementById("fd-principal");
  if (!principal) return;  // window-closed message → nothing to wire
  const term    = document.getElementById("fd-term");
  const preview = document.getElementById("fd-preview");
  function updatePreview() {
    const p = parseFloat(principal.value);
    preview.textContent = (p >= 1)
      ? `→ matures to $${money(fdPayout(p, parseInt(term.value, 10), fdTermRate(term)))}`
      : "";
  }
  principal.addEventListener("input", updatePreview);
  term.addEventListener("change", updatePreview);
  document.getElementById("fd-open-btn").addEventListener("click", async () => {
    const p = parseInt(principal.value, 10);
    if (!p || p < 1) { toast("Enter a principal", "err"); return; }
    try {
      await api("/api/fd/open", "POST", { principal: p, term: parseInt(term.value, 10) });
      toast("FD opened", "ok");
      await refreshMe();   // renders the card and flips fdShown
    } catch (err) { toast(err.message, "err"); }
  });
}

// Close button lives inside the FD card, which is rebuilt every refresh tick;
// delegate from the stable #fd-list so one listener survives every rebuild.
fdList.addEventListener("click", e => {
  if (e.target.closest("#fd-close-btn")) closeFd();
});
async function closeFd() {
  const fd = currentFd;
  if (!fd) return;
  const back = money(fd.close_value_now);
  const msg = fd.matured
    ? `Close matured FD and receive $${back}?`
    : `Close early now? You'll get back $${back} (early-exit penalty rate).`;
  if (!window.confirm(msg)) return;
  try {
    await api("/api/fd/close", "POST");
    toast("FD closed", "ok");
    await refreshMe();
  } catch (err) { toast(err.message, "err"); }
}

// ── Render market list ──────────────────────────────────
function renderMarket(market) {
  marketIds = market.map(s => s.stock_id);
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
        <span class="muted" id="held-${s.stock_id}">you hold: 0</span>
        <input type="number" min="1" value="1" id="shares-${s.stock_id}" placeholder="qty" />
        <button class="btn btn--success btn--sm" data-sid="${s.stock_id}" data-side="buy">Buy</button>
        <button class="btn btn--danger btn--sm"  data-sid="${s.stock_id}" data-side="sell">Sell</button>
      </div>`;
    marketList.appendChild(div);
  }
  updateHeldDisplays();

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

// Refresh the per-row "you hold: N" labels from heldShares. Safe to call before
// the market rows exist (the elements simply aren't found yet).
function updateHeldDisplays() {
  for (const sid of marketIds) {
    const el = document.getElementById("held-" + sid);
    if (el) el.textContent = "you hold: " + count(heldShares[sid] || 0);
  }
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
