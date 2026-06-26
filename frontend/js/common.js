export async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
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
export function stream(onPrices, onNews) {
  const es = new EventSource("/api/stream");
  es.addEventListener("prices", e => onPrices(JSON.parse(e.data)));
  es.addEventListener("news", e => onNews(JSON.parse(e.data)));
  return es;
}
