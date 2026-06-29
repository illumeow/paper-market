import { api, stream, money as fmt } from "./common.js";

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
const summaryCards = {}; // stock_id -> { priceEl, pctEl, volEl }
const initPrice = {}; // stock_id -> init_price, for the (0, init) chart anchor

// ── Render fused tiles (price + pct + vol + chart per stock) ─
const tilesGrid = document.getElementById("tiles-grid");
function renderTiles(stocks) {
  // Build-once: each tile owns a Chart instance that SSE appends live points to.
  // Re-running this would recreate the Chart and wipe those points, so load()
  // is the only caller; pollDashboard refreshes numbers via updateCards instead.
  tilesGrid.innerHTML = "";
  for (const s of stocks) {
    const pctClass = s.pct_change >= 0 ? "pos" : "neg";
    const pctSign  = s.pct_change >= 0 ? "+" : "";
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.innerHTML = `
      <div class="t-head">
        <span class="s-name">${s.name} <span class="muted">${s.stock_id}</span></span>
        <span class="s-pct ${pctClass}" id="sum-pct-${s.stock_id}">${pctSign}${s.pct_change.toFixed(2)}%</span>
      </div>
      <div class="s-price" id="sum-price-${s.stock_id}">$${fmt(s.price)}</div>
      <div class="s-vol" id="sum-vol-${s.stock_id}">Vol: ${s.volume.toLocaleString()}</div>
      <div class="t-chart"><canvas id="chart-${s.stock_id}"></canvas></div>`;
    tilesGrid.appendChild(tile);
    summaryCards[s.stock_id] = {
      priceEl: tile.querySelector(`#sum-price-${s.stock_id}`),
      pctEl:   tile.querySelector(`#sum-pct-${s.stock_id}`),
      volEl:   tile.querySelector(`#sum-vol-${s.stock_id}`),
    };
    buildChart(s);
  }
}

// In-place number refresh used by the 15s poll — never rebuilds tiles/charts.
function updateCards(stocks) {
  for (const s of stocks) {
    const card = summaryCards[s.stock_id];
    if (!card) continue;
    card.priceEl.textContent = "$" + fmt(s.price);
    const pct = s.pct_change;
    card.pctEl.textContent = (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
    card.pctEl.className = "s-pct " + (pct >= 0 ? "pos" : "neg");
    card.volEl.textContent = "Vol: " + s.volume.toLocaleString();
  }
}

function buildChart(s) {
  initPrice[s.stock_id] = s.init_price;
  const points = s.history.map(h => ({ x: minSinceKickoff(h.ts), y: h.price }));
  // Start the line at (0, init_price): history's first row is the first tick
  // (x≈0.04), not kickoff, so without this the line floats off the left edge.
  if (eventStart != null && points.length && points[0].x > 1e-6) {
    points.unshift({ x: 0, y: s.init_price });
  }
  // Anchor x at kickoff (0) and end at the latest point so the line spans full
  // width. maxX stays undefined pre-kickoff (no data) so the axis auto-sizes.
  const maxX = points.length ? points[points.length - 1].x : undefined;

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
      maintainAspectRatio: false,   // fill the tile's CSS height (projection grows, phone fixes)
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => "$" + fmt(ctx.parsed.y) } },
      },
      scales: {
        x: {
          type: "linear",
          min: 0,
          max: maxX,
          // Label only whole event-minutes: 0,1,…,floor(max). step snaps to a
          // nice value keeping ≤ 8 gaps (e.g. a 120-min event → 15).
          afterBuildTicks: (axis) => {
            const hi = Math.floor(axis.max || 0);
            const NICE = [1, 2, 5, 10, 15, 20, 30, 60, 120, 240];
            let step = NICE[NICE.length - 1];
            for (const s of NICE) { if (Math.floor(hi / s) <= 8) { step = s; break; } }
            const ticks = [];
            for (let v = 0; v <= hi; v += step) ticks.push({ value: v });
            axis.ticks = ticks;
          },
          ticks: { color: "#8892a4", maxRotation: 0, autoSkip: false },
          grid:  { color: "#2e3350" },
        },
        y: {
          ticks: { color: "#8892a4", callback: v => Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }) },
          grid:  { color: "#2e3350" },
        },
      },
    },
  });
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
  // x comes from the server's tick `elapsed` (event-minutes), the same basis as
  // the history points — NOT from the client clock + polled eventStart, which is
  // null/stale for up to one poll after kickoff and would pile early points at 0.
  const nowMin = updates.length ? updates[0].elapsed : null;
  // Tick pushes carry server `elapsed` → keep the status line live every tick.
  // Trade pushes have no elapsed (nowMin null) and must not touch it.
  if (nowMin != null) updateEventStatus(true, nowMin, false);
  for (const u of updates) {
    // Update summary card: price, pct-change (from init_price), and volume
    const card = summaryCards[u.stock_id];
    if (card) {
      card.priceEl.textContent = "$" + fmt(u.price);
      const ip = initPrice[u.stock_id];
      if (ip) {
        const pct = (u.price / ip - 1) * 100;
        card.pctEl.textContent = (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
        card.pctEl.className = "s-pct " + (pct >= 0 ? "pos" : "neg");
      }
      if (u.volume != null) card.volEl.textContent = "Vol: " + u.volume.toLocaleString();
    }

    // Append to chart
    const chart = charts[u.stock_id];
    if (chart && nowMin != null) {
      const ds = chart.data.datasets[0].data;
      // Dashboard opened before kickoff → chart starts empty; anchor the first
      // live point back to (0, init_price) so the line begins at the left edge.
      if (ds.length === 0 && initPrice[u.stock_id] != null) {
        ds.push({ x: 0, y: initPrice[u.stock_id] });
      }
      ds.push({ x: nowMin, y: u.price });
      // Keep enough to span the whole event: ~120min / 5s tick ≈ 1440 points, so
      // trimming below that would empty the left while min stays pinned at 0.
      if (ds.length > 2000) ds.shift();
      // Track the right edge to the newest point so the line always reaches the
      // axis end (mirrors the min:0 / max:last anchoring set in buildChart).
      chart.options.scales.x.max = nowMin;
      chart.update("none");
    }
  }
  document.getElementById("last-update").textContent =
    "Updated " + new Date().toLocaleTimeString();
}

// ── Stream with auto-reconnect ────────────────────────────
function connectStream() {
  const es = stream(onPrices, n => prependNews(n),
    d => updateEventStatus(d.started, d.elapsed_min, d.paused));
  es.onerror = () => {
    es.close();
    setTimeout(connectStream, 3000);
  };
}

// ── Event status indicator ────────────────────────────────
const eventStatusEl = document.getElementById("event-status");

function updateEventStatus(started, elapsed_min, paused) {
  if (!started) {
    eventStatusEl.textContent = "⏳ Event not started";
    eventStatusEl.style.color = "var(--yellow)";
    return;
  }
  const elapsed = Math.round(elapsed_min);
  if (paused) {
    eventStatusEl.textContent = `⏸ Paused · elapsed ${elapsed} min`;
    eventStatusEl.style.color = "var(--yellow)";
  } else {
    eventStatusEl.textContent = `● Live · elapsed ${elapsed} min`;
    eventStatusEl.style.color = "var(--green)";
  }
}

// ── Periodic poll (every 15s) to pick up kickoff transition ──
async function pollDashboard() {
  try {
    const data = await api("/api/dashboard");
    eventStart = data.event_start;
    timeScale = data.time_scale ?? 1;
    updateEventStatus(data.started, data.elapsed_min, data.paused);
    // Optionally refresh summary and news too
    if (data.stocks && data.stocks.length > 0) updateCards(data.stocks);
    if (data.news) renderNews(data.news);
  } catch (_) { /* ignore poll errors silently */ }
}

// ── Load ──────────────────────────────────────────────────
async function load() {
  try {
    const data = await api("/api/dashboard");
    eventStart = data.event_start;
    timeScale = data.time_scale ?? 1;
    updateEventStatus(data.started, data.elapsed_min, data.paused);
    renderTiles(data.stocks);
    renderNews(data.news);
    connectStream();
    // Start periodic poll every 15s
    setInterval(pollDashboard, 15000);
  } catch (err) {
    toast(err.message, "err");
  }
}

load();
