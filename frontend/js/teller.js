import { api, money, count, ratePct, fdPayout, fdTermSelect, fdTermRate } from "/js/common.js";

// ── Toast ────────────────────────────────────────────────
const toastEl = document.getElementById("toast");
let toastTimer;
function toast(msg, type = "ok") {
  clearTimeout(toastTimer);
  toastEl.textContent = msg;
  toastEl.className = `show toast-${type}`;
  toastTimer = setTimeout(() => { toastEl.className = ""; }, 3500);
}

// ── DOM refs ─────────────────────────────────────────────
const loginSection    = document.getElementById("login-section");
const appSection      = document.getElementById("app-section");
const staffPw         = document.getElementById("staff-pw");
const loginBtn        = document.getElementById("login-btn");
const exportBtn       = document.getElementById("export-btn");
const memberIdInput   = document.getElementById("member-id-input");
const lookupBtn       = document.getElementById("lookup-btn");
const memberPanel     = document.getElementById("member-panel");
const lockedPanel     = document.getElementById("locked-panel");
const unlockedPanel   = document.getElementById("unlocked-panel");
const countdownEl     = document.getElementById("countdown-display");
const memberTitle     = document.getElementById("member-title");
const mBalance        = document.getElementById("m-balance");
const mDebt           = document.getElementById("m-debt");
const mHoldingsList   = document.getElementById("m-holdings-list");
const mFdList         = document.getElementById("m-fd-list");
const fdOps           = document.getElementById("fd-ops");

// ── Current member state ─────────────────────────────────
const SNAP_KEY = "pm_teller_member";
let currentMid = null;
let currentDebt = 0;
let countdownInterval = null;
let cooldownDeadline = null;

// ── Login ────────────────────────────────────────────────
loginBtn.addEventListener("click", async () => {
  loginBtn.disabled = true;
  try {
    await api("/api/login/staff", "POST", { password: staffPw.value });
    loginSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    loadEventStatus();
    loadStocks();
    restoreSnapshot();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    loginBtn.disabled = false;
  }
});
staffPw.addEventListener("keydown", e => { if (e.key === "Enter") loginBtn.click(); });

// ── Export ───────────────────────────────────────────────
exportBtn.addEventListener("click", () => { window.location = "/api/export"; });

// ── Logout ───────────────────────────────────────────────
document.getElementById("logout-btn").addEventListener("click", async () => {
  try { await api("/api/logout", "POST"); } catch (_) { /* clear locally regardless */ }
  sessionStorage.removeItem(SNAP_KEY);
  location.reload();  // re-runs the session probe → no cookie → login screen
});

// ── Close lookup ──────────────────────────────────────────
document.getElementById("close-lookup-btn").addEventListener("click", () => {
  sessionStorage.removeItem(SNAP_KEY);
  currentMid = null;
  memberPanel.classList.add("hidden");
  memberIdInput.value = "";
});

// ── Lookup ───────────────────────────────────────────────
lookupBtn.addEventListener("click", async () => {
  const mid = memberIdInput.value.trim();
  if (!mid) { toast("Enter a member ID", "err"); return; }
  lookupBtn.disabled = true;
  try {
    const data = await api(`/api/member/${encodeURIComponent(mid)}`);
    currentMid = mid;
    memberPanel.classList.remove("hidden");
    if (data.locked) {
      showLocked(data.cooldown_remaining_sec);
    } else {
      showUnlocked(data);
    }
  } catch (err) {
    toast(err.message, "err");
  } finally {
    lookupBtn.disabled = false;
  }
});
memberIdInput.addEventListener("keydown", e => { if (e.key === "Enter") lookupBtn.click(); });

// ── Show locked ───────────────────────────────────────────
function showLocked(remaining) {
  lockedPanel.classList.remove("hidden");
  unlockedPanel.classList.add("hidden");
  clearInterval(countdownInterval);
  cooldownDeadline = Date.now() + remaining * 1000;
  updateCountdown();
  countdownInterval = setInterval(updateCountdown, 1000);
}
function updateCountdown() {
  if (cooldownDeadline == null) return;
  const secs = Math.max(0, Math.ceil((cooldownDeadline - Date.now()) / 1000));
  countdownEl.textContent = secs;
  if (secs <= 0) {
    clearInterval(countdownInterval);
    cooldownDeadline = null;
    toast("Cooldown expired — refresh the lookup", "ok");
  }
}

// ── Show unlocked ─────────────────────────────────────────
function showUnlocked(data) {
  clearInterval(countdownInterval);
  cooldownDeadline = null;
  lockedPanel.classList.add("hidden");
  unlockedPanel.classList.remove("hidden");

  currentMid = data.member_id;
  memberTitle.textContent = "Member: " + data.member_id;
  mBalance.textContent = "$" + money(data.balance);
  mDebt.textContent    = data.debt > 0 ? "$" + money(data.debt) : "—";
  // Holdings
  if (data.holdings && data.holdings.length > 0) {
    mHoldingsList.innerHTML = data.holdings.map(h =>
      `<div class="row row--between" style="padding:4px 0;border-bottom:1px solid var(--border)">
        <span>${h.stock_id}</span><span>${count(h.shares)} shares</span>
      </div>`
    ).join("");
  } else {
    mHoldingsList.innerHTML = '<span class="muted">No holdings.</span>';
  }

  // Loan/Repay unified UI
  currentDebt = data.debt || 0;
  const lrBtn  = document.getElementById("loan-repay-btn");
  const lrNote = document.getElementById("loan-repay-note");
  if (currentDebt > 0) {
    lrBtn.textContent = "Repay";
    lrBtn.className = "btn btn--neutral btn--sm";
    lrNote.textContent = `Owes $${money(currentDebt)} (incl. accrued interest)`;
  } else {
    lrBtn.textContent = "Issue Loan";
    lrBtn.className = "btn btn--primary btn--sm";
    lrNote.textContent = "";
  }

  renderMemberFd(data);   // the FD card (payout + countdown)
  renderFdOps(data);      // open form when none, close button when one is open
  sessionStorage.setItem(SNAP_KEY, JSON.stringify(data));
}

// ── FD card (read-only details for the looked-up member) ──
function renderMemberFd(data) {
  const fd = data.fixed_deposits && data.fixed_deposits[0];
  if (!fd) { mFdList.innerHTML = ""; return; }  // no FD → the open form (in #fd-ops below) is the content
  const status = fd.matured
    ? '<span class="pos">✓ Matured</span>'
    : `matures in ${Math.max(0, Math.ceil(fd.remaining_min))} min`;
  mFdList.innerHTML = `<table class="fd-table"><tbody>
    <tr><td>Principal</td><td>$${money(fd.principal)}</td></tr>
    <tr><td>Term</td><td>${fd.term_minutes} min · ${ratePct(fd.rate_per_min)}/min</td></tr>
    <tr><td>Matures to</td><td>$${money(fd.payout)}</td></tr>
    <tr><td>Status</td><td>${status}</td></tr>
  </tbody></table>`;
}

// ── FD operations: open chooser+preview, or a single Close button ──
function renderFdOps(data) {
  if (data.fixed_deposits && data.fixed_deposits.length > 0) {
    const fd = data.fixed_deposits[0];
    fdOps.innerHTML = '<div class="fd-actions-right"><button class="btn btn--danger btn--sm" id="fd-close-btn">Close FD</button></div>';
    document.getElementById("fd-close-btn").addEventListener("click", () => {
      const back = money(fd.close_value_now);
      const msg = fd.matured
        ? `Close matured FD and credit $${back} to the member?`
        : `Close early now? Member gets back $${back} (early-exit penalty rate).`;
      if (!window.confirm(msg)) return;
      tellerOp("/api/teller/fd/close", {}, "FD closed");
    });
    return;
  }
  const opts = (data.fd_options || []).filter(o => data.elapsed_min + o.term <= data.event_duration_min);
  if (opts.length === 0) {
    fdOps.innerHTML = '<span class="muted">FD window closed — too close to event end.</span>';
    return;
  }
  fdOps.innerHTML = `
    <div class="fd-open-row">
      <input type="number" min="1" id="fd-principal" placeholder="Amount" />
      ${fdTermSelect(opts)}
    </div>
    <div class="fd-open-actions">
      <span class="muted" id="fd-preview"></span>
      <button class="btn btn--primary btn--sm" id="fd-open-btn">Open FD</button>
    </div>`;
  const principal = document.getElementById("fd-principal");
  const term      = document.getElementById("fd-term");
  const preview   = document.getElementById("fd-preview");
  function updatePreview() {
    const p = parseFloat(principal.value);
    preview.textContent = (p >= 1)
      ? `→ matures to $${money(fdPayout(p, parseInt(term.value, 10), fdTermRate(term)))}`
      : "";
  }
  principal.addEventListener("input", updatePreview);
  term.addEventListener("change", updatePreview);
  document.getElementById("fd-open-btn").addEventListener("click", async () => {
    if (!currentMid) { toast("Lookup a member first", "err"); return; }
    const p = parseInt(principal.value, 10);
    if (!p || p < 1) { toast("Enter a principal", "err"); return; }
    await tellerOp("/api/teller/fd/open", { principal: p, term: parseInt(term.value, 10) }, "FD opened");
  });
}

// ── Generic teller op helper ──────────────────────────────
function clearInputs(...ids) {
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
}

async function tellerOp(endpoint, body, successMsg, clearIds = []) {
  if (!currentMid) { toast("Lookup a member first", "err"); return; }
  try {
    // The op returns the fresh member snapshot — refresh from it directly.
    // A re-lookup would re-hit the cooldown gate and leave the panel stale.
    const res = await api(endpoint, "POST", { id: currentMid, ...body });
    toast(successMsg, "ok");
    if (res.member) showUnlocked(res.member);
    clearInputs(...clearIds);
  } catch (err) {
    toast(err.message, "err");
  }
}

// ── Cash operations ───────────────────────────────────────
function amtOf(id) {
  const v = parseInt(document.getElementById(id).value, 10);
  if (!v || v < 1) throw new Error("Enter a valid amount");
  return v;
}

document.getElementById("deposit-btn").addEventListener("click", async () => {
  try { await tellerOp("/api/teller/deposit", { amount: amtOf("deposit-amt") }, "Deposit successful", ["deposit-amt"]); }
  catch (e) { toast(e.message, "err"); }
});

document.getElementById("withdraw-btn").addEventListener("click", async () => {
  try { await tellerOp("/api/teller/withdraw", { amount: amtOf("withdraw-amt") }, "Withdrawal successful", ["withdraw-amt"]); }
  catch (e) { toast(e.message, "err"); }
});

document.getElementById("loan-repay-btn").addEventListener("click", async () => {
  try {
    const amt = amtOf("loan-repay-amt");
    if (currentDebt > 0)
      await tellerOp("/api/teller/repay", { amount: amt }, "Repayment recorded", ["loan-repay-amt"]);
    else
      await tellerOp("/api/teller/loan", { amount: amt }, "Loan issued", ["loan-repay-amt"]);
  } catch (e) { toast(e.message, "err"); }
});

// FD open/close handlers are wired per-lookup inside renderFdOps (markup is dynamic).

// ── Trade on behalf ───────────────────────────────────────
async function tradeBehalf(side) {
  if (!currentMid) { toast("Lookup a member first", "err"); return; }
  const stock_id = document.getElementById("trade-stock").value.trim();
  const shares   = parseInt(document.getElementById("trade-shares").value, 10);
  if (!stock_id || !shares) { toast("Enter stock and shares", "err"); return; }
  try {
    const res = await api("/api/teller/trade", "POST", { id: currentMid, stock_id, side, shares });
    toast(`${side === "buy" ? "Bought" : "Sold"} ${res.shares} shares @ $${money(res.price)}`, "ok");
    if (res.member) showUnlocked(res.member);
    clearInputs("trade-shares");
  } catch (err) {
    toast(err.message, "err");
  }
}
document.getElementById("trade-buy-btn").addEventListener("click",  () => tradeBehalf("buy"));
document.getElementById("trade-sell-btn").addEventListener("click", () => tradeBehalf("sell"));

// ── Stocks dropdown ───────────────────────────────────────
async function loadStocks() {
  try {
    const market = await api("/api/market");
    const sel = document.getElementById("trade-stock");
    sel.innerHTML = market.map(s => `<option value="${s.stock_id}">${s.name} (${s.stock_id})</option>`).join("");
  } catch (_) { /* leave empty; trade will validate */ }
}

// ── News publish ──────────────────────────────────────────
document.getElementById("news-btn").addEventListener("click", async () => {
  const text = document.getElementById("news-text").value.trim();
  if (!text) { toast("Enter news text", "err"); return; }
  try {
    await api("/api/teller/news", "POST", { text });
    toast("News published", "ok");
    document.getElementById("news-text").value = "";
  } catch (err) {
    toast(err.message, "err");
  }
});

// ── Event Control ─────────────────────────────────────────
// Three states from {started, paused}: not-started → Start; running → Pause;
// paused → Resume (the start endpoint doubles as resume).
const eventStatusLine = document.getElementById("event-status-line");
const startEventBtn   = document.getElementById("start-event-btn");
const stopEventBtn    = document.getElementById("stop-event-btn");

function renderEventControl(data) {
  const elapsed = Math.round(data.elapsed_min || 0);
  if (!data.started) {
    eventStatusLine.textContent = "Event not started.";
    eventStatusLine.className = "muted";
    startEventBtn.textContent = "Start Event";
    startEventBtn.style.display = "";
    stopEventBtn.style.display = "none";
  } else if (data.paused) {
    eventStatusLine.textContent = `Event paused — elapsed ${elapsed} min`;
    eventStatusLine.className = "muted";
    startEventBtn.textContent = "Resume Event";
    startEventBtn.style.display = "";
    stopEventBtn.style.display = "none";
  } else {
    eventStatusLine.textContent = `Event running — elapsed ${elapsed} min`;
    eventStatusLine.className = "pos";
    startEventBtn.style.display = "none";
    stopEventBtn.style.display = "";
  }
}

async function loadEventStatus() {
  try {
    renderEventControl(await api("/api/dashboard"));
  } catch (err) {
    eventStatusLine.textContent = "Could not load event status.";
    eventStatusLine.className = "muted";
  }
}

startEventBtn.addEventListener("click", async () => {
  const resuming = startEventBtn.textContent.includes("Resume");
  startEventBtn.disabled = true;
  try {
    const res = await api("/api/teller/start", "POST");
    renderEventControl({ started: true, paused: false, elapsed_min: res.elapsed_min });
    toast(resuming ? "Event resumed!" : "Event started!", "ok");
  } catch (err) {
    toast(err.message, "err");
  } finally {
    startEventBtn.disabled = false;
  }
});

stopEventBtn.addEventListener("click", async () => {
  if (!window.confirm("Pause the event? Market, trading, and all interest/FD accrual freeze. Resume anytime with Start.")) return;
  stopEventBtn.disabled = true;
  try {
    const res = await api("/api/teller/stop", "POST");
    renderEventControl(res);
    toast("Event paused.", "ok");
  } catch (err) {
    toast(err.message, "err");
  } finally {
    stopEventBtn.disabled = false;
  }
});

// ── Snapshot restore helper ───────────────────────────────
function restoreSnapshot() {
  const saved = sessionStorage.getItem(SNAP_KEY);
  if (saved) {
    try {
      const d = JSON.parse(saved);
      memberPanel.classList.remove("hidden");
      showUnlocked(d);
    } catch (_) {
      sessionStorage.removeItem(SNAP_KEY);
    }
  }
}

// ── Cooldown tab-focus fix ────────────────────────────────
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && cooldownDeadline != null) updateCountdown();
});

// ── Restore staff session on load ─────────────────────────
// The pm_session cookie persists across refresh but is httponly, so JS can't
// read it — probe a staff-only endpoint. If valid, skip the login screen.
(async () => {
  try {
    await api("/api/teller/session");
    loginSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    loadEventStatus();
    loadStocks();
    restoreSnapshot();
  } catch (_) { /* not logged in — leave login screen up */ }
})();
