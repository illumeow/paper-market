import { api, stream, money as fmt } from "/js/common.js";

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
function minSinceKickoff(ts) {
  if (eventStart == null) return 0;
  return (ts - eventStart) / 60 * timeScale;   // event-minutes (backend TIME_SCALE)
}

// ── State ────────────────────────────────────────────────
let eventStart = null;
let timeScale = 1;   // event-minutes per real-minute; from /api/dashboard (TIME_SCALE)
const charts = {}; // stock_id -> Chart instance
const summaryCards = {}; // stock_id -> { priceEl, pctEl }

// ── Render summary ────────────────────────────────────────
const summaryGrid = document.getElementById("summary-grid");
function renderSummary(stocks) {
  summaryGrid.innerHTML = "";
  for (const s of stocks) {
    const pctClass = s.pct_change >= 0 ? "pos" : "neg";
    const pctSign  = s.pct_change >= 0 ? "+" : "";
    const div = document.createElement("div");
    div.className = "summary-card";
    div.innerHTML = `
      <div class="s-name">${s.name} <span class="muted">${s.stock_id}</span></div>
      <div class="s-price" id="sum-price-${s.stock_id}">$${fmt(s.price)}</div>
      <div class="s-pct ${pctClass}" id="sum-pct-${s.stock_id}">${pctSign}${s.pct_change.toFixed(2)}%</div>
      <div class="s-vol">Vol: ${s.volume.toLocaleString()}</div>`;
    summaryGrid.appendChild(div);
    summaryCards[s.stock_id] = {
      priceEl: div.querySelector(`#sum-price-${s.stock_id}`),
      pctEl:   div.querySelector(`#sum-pct-${s.stock_id}`),
    };
  }
}

// ── Render charts ─────────────────────────────────────────
const chartsGrid = document.getElementById("charts-grid");
function renderCharts(stocks) {
  chartsGrid.innerHTML = "";
  for (const s of stocks) {
    const card = document.createElement("div");
    card.className = "chart-card";
    card.innerHTML = `<h3>${s.name} <span class="muted">(${s.stock_id})</span></h3>
      <canvas id="chart-${s.stock_id}" height="180"></canvas>`;
    chartsGrid.appendChild(card);

    const points = s.history.map(h => ({ x: minSinceKickoff(h.ts), y: h.price }));

    const ctx = document.getElementById(`chart-${s.stock_id}`).getContext("2d");
    charts[s.stock_id] = new Chart(ctx, {
      type: "line",
      data: {
        datasets: [{
          label: s.name,
          data: points,
          borderColor: "#6c8cff",
          backgroundColor: "rgba(108,140,255,.12)",
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 0,
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => "$" + fmt(ctx.parsed.y),
            },
          },
        },
        scales: {
          x: {
            type: "linear",
            ticks: { color: "#8892a4", precision: 0, maxTicksLimit: 8, maxRotation: 0 },
            grid:  { color: "#2e3350" },
          },
          y: {
            ticks: { color: "#8892a4", callback: v => fmt(v) },
            grid:  { color: "#2e3350" },
          },
        },
      },
    });
  }
}

// ── Render news ───────────────────────────────────────────
const newsFeed = document.getElementById("news-feed");
function renderNews(newsItems) {
  if (!newsItems || newsItems.length === 0) {
    newsFeed.innerHTML = '<span class="muted">No news yet.</span>';
    return;
  }
  newsFeed.innerHTML = newsItems.slice(0, 10).map(n => `
    <div class="news-item">
      <div>${escapeHtml(n.text)}</div>
    </div>`
  ).join("");
}

function prependNews(n) {
  const div = document.createElement("div");
  div.className = "news-item";
  div.innerHTML = `<div>${escapeHtml(n.text)}</div>`;
  newsFeed.insertBefore(div, newsFeed.firstChild);
  // Keep max 15
  while (newsFeed.children.length > 15) newsFeed.removeChild(newsFeed.lastChild);
}

function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Live price update ─────────────────────────────────────
function onPrices(updates) {
  const nowMin = minSinceKickoff(Date.now() / 1000);
  for (const u of updates) {
    // Update summary card
    const card = summaryCards[u.stock_id];
    if (card) card.priceEl.textContent = "$" + fmt(u.price);

    // Append to chart
    const chart = charts[u.stock_id];
    if (chart) {
      const ds = chart.data.datasets[0].data;
      ds.push({ x: nowMin, y: u.price });
      // Keep last 200 points
      if (ds.length > 200) ds.shift();
      chart.update("none");
    }
  }
  document.getElementById("last-update").textContent =
    "Updated " + new Date().toLocaleTimeString();
}

// ── Stream with auto-reconnect ────────────────────────────
function connectStream() {
  const es = stream(onPrices, n => prependNews(n));
  es.onerror = () => {
    es.close();
    setTimeout(connectStream, 3000);
  };
}

// ── Event status indicator ────────────────────────────────
const eventStatusEl = document.getElementById("event-status");

function updateEventStatus(started, elapsed_min) {
  if (started) {
    const elapsed = Math.round(elapsed_min);
    eventStatusEl.textContent = `● Live · elapsed ${elapsed} min`;
    eventStatusEl.style.color = "var(--green)";
  } else {
    eventStatusEl.textContent = "⏳ Event not started";
    eventStatusEl.style.color = "var(--yellow)";
  }
}

// ── Periodic poll (every 15s) to pick up kickoff transition ──
async function pollDashboard() {
  try {
    const data = await api("/api/dashboard");
    eventStart = data.event_start;
    timeScale = data.time_scale ?? 1;
    updateEventStatus(data.started, data.elapsed_min);
    // Optionally refresh summary and news too
    if (data.stocks && data.stocks.length > 0) renderSummary(data.stocks);
    if (data.news) renderNews(data.news);
  } catch (_) { /* ignore poll errors silently */ }
}

// ── Load ──────────────────────────────────────────────────
async function load() {
  try {
    const data = await api("/api/dashboard");
    eventStart = data.event_start;
    timeScale = data.time_scale ?? 1;
    updateEventStatus(data.started, data.elapsed_min);
    renderSummary(data.stocks);
    renderCharts(data.stocks);
    renderNews(data.news);
    connectStream();
    // Start periodic poll every 15s
    setInterval(pollDashboard, 15000);
  } catch (err) {
    toast(err.message, "err");
  }
}

load();
