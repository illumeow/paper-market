import { api } from "/js/common.js";

// ── Toast ────────────────────────────────────────────────
const toastEl = document.getElementById("toast");
let toastTimer;
function toast(msg, type = "ok") {
  clearTimeout(toastTimer);
  toastEl.textContent = msg;
  toastEl.className = `show toast-${type}`;
  toastTimer = setTimeout(() => { toastEl.className = ""; }, 3500);
}

// ── Formatting ───────────────────────────────────────────
function fmt(n) { return Number(n).toLocaleString(undefined, { minimumFractionDigits: 0 }); }

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
const mReliefStatus   = document.getElementById("m-relief-status");
const mHoldingsList   = document.getElementById("m-holdings-list");
const mFdList         = document.getElementById("m-fd-list");
const reliefNote      = document.getElementById("relief-note");

// ── Current member state ─────────────────────────────────
let currentMid = null;
let countdownInterval = null;

// ── Login ────────────────────────────────────────────────
loginBtn.addEventListener("click", async () => {
  loginBtn.disabled = true;
  try {
    await api("/api/login/staff", "POST", { password: staffPw.value });
    loginSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    loadEventStatus();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    loginBtn.disabled = false;
  }
});
staffPw.addEventListener("keydown", e => { if (e.key === "Enter") loginBtn.click(); });

// ── Export ───────────────────────────────────────────────
exportBtn.addEventListener("click", () => { window.location = "/api/export"; });

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
  let secs = remaining;
  countdownEl.textContent = secs;
  countdownInterval = setInterval(() => {
    secs--;
    if (secs <= 0) {
      clearInterval(countdownInterval);
      countdownEl.textContent = "0";
      toast("Cooldown expired — refresh the lookup", "ok");
    } else {
      countdownEl.textContent = secs;
    }
  }, 1000);
}

// ── Show unlocked ─────────────────────────────────────────
function showUnlocked(data) {
  clearInterval(countdownInterval);
  lockedPanel.classList.add("hidden");
  unlockedPanel.classList.remove("hidden");

  memberTitle.textContent = "Member: " + data.member_id;
  mBalance.textContent = "$" + fmt(data.balance);
  mDebt.textContent    = data.debt > 0 ? "$" + fmt(data.debt) : "—";
  mReliefStatus.textContent = data.relief_claimed ? "Relief already claimed." : "";
  reliefNote.textContent    = data.relief_claimed ? "(already claimed)" : "";

  // Holdings
  if (data.holdings && data.holdings.length > 0) {
    mHoldingsList.innerHTML = data.holdings.map(h =>
      `<div class="row row--between" style="padding:4px 0;border-bottom:1px solid var(--border)">
        <span>${h.stock_id}</span><span>${fmt(h.shares)} shares</span>
      </div>`
    ).join("");
  } else {
    mHoldingsList.innerHTML = '<span class="muted">No holdings.</span>';
  }

  // FDs
  if (data.fixed_deposits && data.fixed_deposits.length > 0) {
    const rows = data.fixed_deposits.map(f =>
      `<tr>
        <td>${f.fd_id}</td>
        <td>$${fmt(f.principal)}</td>
        <td>${f.term_minutes}min</td>
      </tr>`
    ).join("");
    mFdList.innerHTML = `<table class="fd-table">
      <thead><tr><th>ID</th><th>Principal</th><th>Term</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  } else {
    mFdList.innerHTML = '<span class="muted">No open FDs.</span>';
  }
}

// ── Generic teller op helper ──────────────────────────────
async function tellerOp(endpoint, body, successMsg) {
  if (!currentMid) { toast("Lookup a member first", "err"); return; }
  try {
    await api(endpoint, "POST", { id: currentMid, ...body });
    toast(successMsg, "ok");
    // Re-fetch to refresh balances
    const data = await api(`/api/member/${encodeURIComponent(currentMid)}`);
    if (!data.locked) showUnlocked(data);
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
  try { await tellerOp("/api/teller/deposit", { amount: amtOf("deposit-amt") }, "Deposit successful"); }
  catch (e) { toast(e.message, "err"); }
});

document.getElementById("withdraw-btn").addEventListener("click", async () => {
  try { await tellerOp("/api/teller/withdraw", { amount: amtOf("withdraw-amt") }, "Withdrawal successful"); }
  catch (e) { toast(e.message, "err"); }
});

document.getElementById("loan-btn").addEventListener("click", async () => {
  try { await tellerOp("/api/teller/loan", { amount: amtOf("loan-amt") }, "Loan issued"); }
  catch (e) { toast(e.message, "err"); }
});

document.getElementById("repay-btn").addEventListener("click", async () => {
  try { await tellerOp("/api/teller/repay", { amount: amtOf("repay-amt") }, "Repayment recorded"); }
  catch (e) { toast(e.message, "err"); }
});

document.getElementById("relief-btn").addEventListener("click", async () => {
  await tellerOp("/api/teller/relief", {}, "Relief granted");
});

// ── FD operations ─────────────────────────────────────────
document.getElementById("fd-open-btn").addEventListener("click", async () => {
  if (!currentMid) { toast("Lookup a member first", "err"); return; }
  const principal = parseInt(document.getElementById("fd-principal").value, 10);
  const term      = parseInt(document.getElementById("fd-term").value, 10);
  if (!principal || !term) { toast("Enter principal and term", "err"); return; }
  try {
    const res = await api("/api/teller/fd/open", "POST", { id: currentMid, principal, term });
    toast("FD opened: " + res.fd_id, "ok");
    const data = await api(`/api/member/${encodeURIComponent(currentMid)}`);
    if (!data.locked) showUnlocked(data);
  } catch (err) {
    toast(err.message, "err");
  }
});

document.getElementById("fd-close-btn").addEventListener("click", async () => {
  const fdId = document.getElementById("fd-close-id").value.trim();
  if (!fdId) { toast("Enter FD ID", "err"); return; }
  await tellerOp("/api/teller/fd/close", { fd_id: fdId }, "FD closed");
});

// ── Trade on behalf ───────────────────────────────────────
async function tradeBehalf(side) {
  if (!currentMid) { toast("Lookup a member first", "err"); return; }
  const stock_id = document.getElementById("trade-stock").value.trim();
  const shares   = parseInt(document.getElementById("trade-shares").value, 10);
  if (!stock_id || !shares) { toast("Enter stock and shares", "err"); return; }
  try {
    const res = await api("/api/teller/trade", "POST", { id: currentMid, stock_id, side, shares });
    toast(`${side === "buy" ? "Bought" : "Sold"} ${res.shares} shares @ $${fmt(res.price)}`, "ok");
    const data = await api(`/api/member/${encodeURIComponent(currentMid)}`);
    if (!data.locked) showUnlocked(data);
  } catch (err) {
    toast(err.message, "err");
  }
}
document.getElementById("trade-buy-btn").addEventListener("click",  () => tradeBehalf("buy"));
document.getElementById("trade-sell-btn").addEventListener("click", () => tradeBehalf("sell"));

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
const eventStatusLine = document.getElementById("event-status-line");
const startEventBtn   = document.getElementById("start-event-btn");

async function loadEventStatus() {
  try {
    const data = await api("/api/dashboard");
    if (data.started) {
      const elapsed = Math.round(data.elapsed_min);
      eventStatusLine.textContent = `Event running — elapsed ${elapsed} min`;
      eventStatusLine.className = "pos";
      startEventBtn.style.display = "none";
    } else {
      eventStatusLine.textContent = "Event not started.";
      eventStatusLine.className = "muted";
      startEventBtn.style.display = "";
    }
  } catch (err) {
    eventStatusLine.textContent = "Could not load event status.";
    eventStatusLine.className = "muted";
  }
}

startEventBtn.addEventListener("click", async () => {
  startEventBtn.disabled = true;
  try {
    const res = await api("/api/teller/start", "POST");
    const elapsed = Math.round(res.elapsed_min);
    eventStatusLine.textContent = `Event running (started just now) — elapsed ${elapsed} min`;
    eventStatusLine.className = "pos";
    startEventBtn.style.display = "none";
    toast("Event started!", "ok");
  } catch (err) {
    toast(err.message, "err");
    startEventBtn.disabled = false;
  }
});

// ── Check if already logged in ────────────────────────────
(async () => {
  try {
    // Attempt a staff-only endpoint probe by calling /api/dashboard (public) is wrong
    // Try /api/member/... won't work w/o a member id.
    // Just show login on load — no silent re-auth for teller.
  } catch (_) { /* pass */ }
})();
