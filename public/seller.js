// Seller dashboard: KPIs, approvals (approve / reject), sales chart, orders, flags, CSV upload.
const API = window.DUKAAN_API || "";
const $ = (id) => document.getElementById(id);
const rs = (n) => "Rs " + Number(n).toLocaleString("en-PK");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let token = "";
try { token = sessionStorage.getItem("dukaan.admin") || ""; } catch {}
let seen = new Set();
let timer = null;

async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { ...opts, headers: { "Content-Type": "application/json", "X-Admin-Token": token, ...(opts.headers || {}) } });
  if (r.status === 401) throw new Error("auth");
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

function items(o) { return o.items.map((i) => `${i.qty} × ${esc(i.name)} (${esc(i.size)})`).join("<br>"); }
function status(s) { return `<span class="badge ${esc(s)}">${esc(s.replace("_", " "))}</span>`; }

function orderRows(list, withActions) {
  if (!list.length) return `<p class="empty">${withActions ? "Nothing waiting. 🎉" : "No orders yet. Place one from the store."}</p>`;
  return `<table><thead><tr><th>Order</th><th>Shopper</th><th>Items</th><th>Total</th><th>City</th><th>Status</th>${withActions ? "<th>Why</th><th></th>" : "<th>When (UTC)</th>"}</tr></thead><tbody>${
    list.map((o) => `<tr class="${seen.has(o.id) ? "" : "new-row"}">
      <td><b>${esc(o.id)}</b></td><td>${esc(o.user_id)}</td><td>${items(o)}</td>
      <td class="num">${rs(o.total)}${o.discount_percent ? `<br><span class="muted">${o.discount_percent}% ${esc(o.discount_status.replace("_", " "))}</span>` : ""}</td>
      <td>${esc(o.city)}</td><td>${status(o.status)}</td>
      ${withActions
        ? `<td class="muted">${esc(o.approval_reason)}</td><td style="white-space:nowrap"><button class="btn small ok" data-act="approve" data-id="${esc(o.id)}">Approve</button> <button class="btn small bad" data-act="reject" data-id="${esc(o.id)}">Reject</button></td>`
        : `<td class="muted">${esc(o.created_at.slice(5, 16))}</td>`}
    </tr>`).join("")}</tbody></table>`;
}

async function refresh() {
  try {
    const [s, orders, flags] = await Promise.all([api("/api/admin/summary"), api("/api/admin/orders"), api("/api/admin/flags")]);
    const kpi = (label, value) => `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`;
    $("kpis").innerHTML = [
      kpi("Revenue", rs(s.revenue)), kpi("Orders", s.orders), kpi("Awaiting you", s.by_status.awaiting_seller || 0),
      kpi("Chats handled", s.chats), kpi("Tokens in / out", `${(s.tokens_in / 1000).toFixed(1)}k / ${(s.tokens_out / 1000).toFixed(1)}k`),
      kpi("Model cost", `$${s.est_cost_usd.toFixed(3)}`), kpi("Avg reply", `${(s.avg_latency_ms / 1000).toFixed(1)}s`),
      kpi("Flagged", s.flags),
    ].join("");
    $("pending").innerHTML = orderRows(orders.filter((o) => o.status === "awaiting_seller"), true);
    $("orders").innerHTML = orderRows(orders, false);
    orders.forEach((o) => seen.add(o.id));

    const max = Math.max(1, ...s.daily_sales.map((d) => d.total));
    $("bars").innerHTML = s.daily_sales.length
      ? s.daily_sales.map((d) => `<div class="bar" style="height:${Math.max(2, (d.total / max) * 100)}%" title="${esc(d.day)}: ${rs(d.total)}"><span>${esc(d.day.slice(5))}</span></div>`).join("")
      : `<p class="empty">No confirmed sales yet.</p>`;
    $("lowstock").innerHTML = s.low_stock.length
      ? `<table><tbody>${s.low_stock.map((p) => `<tr><td><b>${esc(p.sku)}</b> ${esc(p.name)}</td><td class="muted">${esc(Object.entries(p.stock).map(([k, v]) => `${k}:${v}`).join(" "))}</td></tr>`).join("")}</tbody></table>`
      : `<p class="empty">All items well stocked.</p>`;
    $("flags").innerHTML = flags.length
      ? `<table><thead><tr><th>When (UTC)</th><th>Shopper</th><th>Type</th><th>Message</th></tr></thead><tbody>${
          flags.map((f) => `<tr><td class="muted">${esc(f.created_at.slice(5, 16))}</td><td>${esc(f.user_id)}</td><td>${status(f.kind)}</td><td>${esc(f.message)}</td></tr>`).join("")}</tbody></table>`
      : `<p class="empty">No flagged requests.</p>`;
  } catch (e) {
    if (e.message === "auth") return logout("Wrong password.");
  }
}

$("pending").addEventListener("click", async (e) => {
  const { act, id } = e.target.dataset;
  if (!act) return;
  if (act === "reject" && !confirm(`Reject ${id}? Stock will be returned.`)) return;
  e.target.disabled = true;
  try { await api(`/api/admin/orders/${encodeURIComponent(id)}/${act}`, { method: "POST" }); } catch (err) { alert(err.message); }
  refresh();
});

$("upload").addEventListener("click", async () => {
  $("uploadMsg").textContent = "Uploading…";
  try {
    const r = await api("/api/admin/products/csv", { method: "POST", body: JSON.stringify({ csv: $("csv").value }) });
    $("uploadMsg").textContent = `${r.upserted} products saved.`;
  } catch (err) { $("uploadMsg").textContent = err.message; }
});

function show(loggedIn) {
  $("login").hidden = loggedIn; $("dash").hidden = !loggedIn; $("live").hidden = !loggedIn; $("logout").hidden = !loggedIn;
}
function logout(msg) {
  token = ""; try { sessionStorage.removeItem("dukaan.admin"); } catch {}
  clearInterval(timer); show(false); $("loginErr").textContent = msg || "";
}
$("logout").addEventListener("click", () => logout());
$("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  token = $("token").value;
  try { sessionStorage.setItem("dukaan.admin", token); } catch {}
  start();
});

async function start() {
  show(true);
  await refresh();
  if (token) { clearInterval(timer); timer = setInterval(refresh, 5000); }   // new orders appear live
}
if (token) start(); else show(false);
