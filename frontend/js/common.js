// This module is served at <BASE>/js/common.js. Derive <BASE> ("" locally, "/paper-market"
// behind a sub-path proxy) so every absolute API path resolves under the deploy prefix.
const BASE = new URL("..", import.meta.url).pathname.replace(/\/$/, "");
export const url = (path) => BASE + path;

export async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opt);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}
// Money: always 2 decimals, trailing zeros padded (1.1 → "1.10", 1051.141 → "1,051.14").
export function money(n) {
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
// Whole counts (shares, volume): no decimals.
export function count(n) {
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}
// Per-minute rate as a percent, trailing zeros trimmed (0.01 → "1%", 0.015 → "1.5%").
export function ratePct(r) {
  return +(r * 100).toFixed(4) + "%";
}
// FD maturity payout: principal compounded at rate_per_min over the whole term.
export function fdPayout(principal, term, rate) {
  return principal * Math.pow(1 + rate, term);
}
// Term dropdown (compact, mobile-friendly) — each option carries its rate.
export function fdTermSelect(opts, id = "fd-term") {
  const options = opts.map(o =>
    `<option value="${o.term}" data-rate="${o.rate}">${o.term} min · ${ratePct(o.rate)}/min</option>`
  ).join("");
  return `<select id="${id}">${options}</select>`;
}
// Per-minute rate of the currently selected term option.
export function fdTermRate(sel) {
  return parseFloat(sel.selectedOptions[0].dataset.rate);
}
export function stream(onPrices, onNews) {
  const es = new EventSource(BASE + "/api/stream");
  es.addEventListener("prices", e => onPrices(JSON.parse(e.data)));
  es.addEventListener("news", e => onNews(JSON.parse(e.data)));
  return es;
}
