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
const empty = (ic, text) => `<p class="empty">${icon(ic)}${text}</p>`;

function orderRows(list, withActions) {
  if (!list.length) return withActions ? empty("check", "You're all caught up. Nothing is waiting for approval.")
    : empty("inbox", "No orders yet. Orders placed through Noor in the store appear here.");
  return `<table><thead><tr><th>Order</th><th>Shopper</th><th>Items</th><th>Total</th><th>City</th><th>Status</th>${withActions ? "<th>Why</th><th></th>" : "<th>When (UTC)</th>"}</tr></thead><tbody>${
    list.map((o) => `<tr class="${seen.has(o.id) ? "" : "new-row"}">
      <td><b>${esc(o.id)}</b></td><td>${esc(o.user_id)}</td><td>${items(o)}</td>
      <td class="num">${rs(o.total)}${o.discount_percent ? `<br><span class="muted">${o.discount_percent}% ${esc(o.discount_status.replace("_", " "))}</span>` : ""}</td>
      <td>${esc(o.city)}</td><td>${status(o.status)}</td>
      ${withActions
        ? `<td class="muted">${esc(o.approval_reason)}</td><td><div class="actions"><button class="btn small ok" data-act="approve" data-id="${esc(o.id)}">${icon("check")}Approve</button><button class="btn small bad" data-act="reject" data-id="${esc(o.id)}">${icon("x")}Reject</button></div></td>`
        : `<td class="muted">${esc(o.created_at.slice(5, 16))}</td>`}
    </tr>`).join("")}</tbody></table>`;
}

async function refresh() {
  try {
    const [s, orders, flags] = await Promise.all([api("/api/admin/summary"), api("/api/admin/orders"), api("/api/admin/flags")]);
    const waiting = s.by_status.awaiting_seller || 0;
    const kpi = (cls, ic, label, value, hint) => `<div class="kpi ${cls}"><div class="label"><span class="ic">${icon(ic)}</span>${label}</div>`
      + `<div class="value">${value}</div><div class="hint">${hint}</div></div>`;
    $("kpis").innerHTML = [
      kpi("hero-kpi", "wallet", "Revenue", rs(s.revenue), "From confirmed orders"),
      kpi("", "bag", "Orders", s.orders, `${s.by_status.confirmed || 0} confirmed, ${s.by_status.rejected || 0} rejected`),
      kpi(`attention ${waiting ? "has" : ""}`, "clock", "Waiting for you", waiting, waiting ? "Review them below" : "Nothing to review"),
    ].join("");
    const m = (ic, label, value) => `<div class="m">${icon(ic)}<div><small>${label}</small><b>${value}</b></div></div>`;
    $("agent").innerHTML = [
      m("chat", "Chats handled", s.chats.toLocaleString()),
      m("cpu", "Tokens in / out", `${(s.tokens_in / 1000).toFixed(1)}k / ${(s.tokens_out / 1000).toFixed(1)}k`),
      m("cash", "Model cost", `$${s.est_cost_usd.toFixed(3)}`),
      m("zap", "Average reply", `${(s.avg_latency_ms / 1000).toFixed(1)}s`),
      m("shield", "Requests blocked", s.flags),
    ].join("");
    const pending = orders.filter((o) => o.status === "awaiting_seller");
    $("pendingN").textContent = pending.length; $("ordersN").textContent = orders.length; $("flagsN").textContent = flags.length;
    $("pending").innerHTML = orderRows(pending, true);
    $("orders").innerHTML = orderRows(orders, false);
    orders.forEach((o) => seen.add(o.id));

    const max = Math.max(1, ...s.daily_sales.map((d) => d.total));
    $("bars").innerHTML = s.daily_sales.length
      ? s.daily_sales.map((d) => `<div class="bar" style="height:${Math.max(2, (d.total / max) * 100)}%" title="${esc(d.day)}: ${rs(d.total)}"><em>${(d.total / 1000).toFixed(1)}k</em><span>${esc(d.day.slice(5))}</span></div>`).join("")
      : empty("chart", "No confirmed sales yet.");
    $("lowstock").innerHTML = s.low_stock.length
      ? `<table><tbody>${s.low_stock.map((p) => `<tr><td><b>${esc(p.sku)}</b> ${esc(p.name)}</td><td class="muted">${esc(Object.entries(p.stock).map(([k, v]) => `${k}:${v}`).join(" "))}</td></tr>`).join("")}</tbody></table>`
      : empty("check", "Everything is well stocked.");
    $("flags").innerHTML = flags.length
      ? `<table><thead><tr><th>When (UTC)</th><th>Shopper</th><th>Type</th><th>Message</th></tr></thead><tbody>${
          flags.map((f) => `<tr><td class="muted">${esc(f.created_at.slice(5, 16))}</td><td>${esc(f.user_id)}</td><td>${status(f.kind)}</td><td>${esc(f.message)}</td></tr>`).join("")}</tbody></table>`
      : empty("shield", "No flagged requests. The guard hasn't had to block anything.");
  } catch (e) {
    if (e.message === "auth") return logout("That password didn't work. Check it and try again.");
  }
}

$("pending").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const { act, id } = b.dataset;
  if (act === "reject" && !confirm(`Reject ${id}? Its stock goes back on sale.`)) return;
  b.disabled = true;
  try { await api(`/api/admin/orders/${encodeURIComponent(id)}/${act}`, { method: "POST" }); } catch (err) { alert(err.message); }
  refresh();
});

$("upload").addEventListener("click", async () => {
  $("uploadMsg").textContent = "Uploading…";
  try {
    const r = await api("/api/admin/products/csv", { method: "POST", body: JSON.stringify({ csv: $("csv").value }) });
    $("uploadMsg").textContent = `Uploaded ${r.upserted} products.`;
  } catch (err) { $("uploadMsg").textContent = err.message; }
});

function show(loggedIn) {
  $("loginWrap").hidden = loggedIn; $("dash").hidden = !loggedIn; $("live").hidden = !loggedIn; $("logout").hidden = !loggedIn;
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

// ── AdForge (Track 2 bonus): two ad variants per product, tracking links, clicks per variant ──
const adLink = (id) => `${location.origin}/api/ad/${id}`;
let lastAds = [];

function adCard(a, lead) {
  return `<article class="ad-card ${lead ? "lead" : ""}">
    <div class="ad-top"><span class="ad-v">${esc(a.variant)}</span><b>${esc(a.angle)}</b>
      ${lead ? `<span class="lead-badge">${icon("trophy")}Leading</span>` : ""}
      <span class="ad-clicks" data-clicks="${esc(a.id)}">${icon("pointer")}${a.clicks} ${a.clicks === 1 ? "click" : "clicks"}</span></div>
    <pre class="ad-text">${esc(a.text)}</pre>
    <div class="ad-foot"><code>${esc(adLink(a.id))}</code>
      <button class="btn small" data-copy="${esc(a.text + "\n\nOrder here: " + adLink(a.id))}">${icon("copy")}Copy ad</button>
      <button class="btn small ghost" data-copy="${esc(adLink(a.id))}">${icon("link")}Copy link</button></div>
  </article>`;
}

function renderLatest() {
  if (!lastAds.length) { $("adResult").innerHTML = ""; return; }
  const top = Math.max(...lastAds.map((a) => a.clicks));
  $("adResult").innerHTML = lastAds.map((a) => adCard(a, top > 0 && a.clicks === top)).join("");
}

async function loadAdProducts() {
  try {
    const list = await fetch(`${API}/api/products`).then((r) => r.json());
    $("adSku").innerHTML = list.map((p) => `<option value="${esc(p.sku)}">${esc(p.sku)} ${esc(p.name)} (${rs(p.price)})</option>`).join("");
  } catch { $("adMsg").textContent = "Products didn't load. Refresh the page."; }
}

async function refreshAds() {
  try {
    const rows = await api("/api/admin/ads");
    const batches = [];
    rows.forEach((r) => { let b = batches.find((x) => x.batch === r.batch); if (!b) batches.push(b = {batch: r.batch, rows: []}); b.rows.push(r); });
    if (!lastAds.length && batches.length) lastAds = batches[0].rows;
    lastAds = lastAds.map((a) => ({...a, clicks: (rows.find((r) => r.id === a.id) || a).clicks}));
    renderLatest();
    $("adHistory").innerHTML = batches.length ? `<table><thead><tr><th>Campaign</th><th>Product</th><th>Variant A</th><th>Variant B</th><th>Leader</th><th>Created (UTC)</th></tr></thead><tbody>${
      batches.slice(0, 8).map((b) => {
        const [A, B] = ["A", "B"].map((v) => b.rows.find((r) => r.variant === v) || {clicks: 0, angle: ""});
        const lead = A.clicks === B.clicks ? `<span class="muted">Tied</span>` : `<span class="lead-badge">${icon("trophy")}${A.clicks > B.clicks ? "A" : "B"}</span>`;
        return `<tr><td><b>${esc(b.batch)}</b></td><td>${esc(b.rows[0].sku)}</td><td>${esc(A.angle)}<br><span class="muted">${A.clicks} clicks</span></td>`
          + `<td>${esc(B.angle)}<br><span class="muted">${B.clicks} clicks</span></td><td>${lead}</td><td class="muted">${esc(b.rows[0].created_at.slice(5, 16))}</td></tr>`;
      }).join("")}</tbody></table>` : empty("megaphone", "No campaigns yet. Pick a product and write your first two ads.");
  } catch (e) { if (e.message === "auth") logout("That password didn't work. Check it and try again."); }
}

$("adGo").addEventListener("click", async () => {
  const b = $("adGo"); b.disabled = true;
  $("adMsg").textContent = "Writing two ads…";
  try {
    const out = await api("/api/admin/ads", { method: "POST", body: JSON.stringify({ sku: $("adSku").value, occasion: $("adOcc").value }) });
    lastAds = out.ads;
    $("adMsg").innerHTML = `${icon("check")} Two ads ready for ${esc(out.name)}. Audience: ${esc(out.audience)}`;
    renderLatest(); refreshAds();
  } catch (err) { $("adMsg").textContent = err.message === "auth" ? "Log in again." : err.message; }
  b.disabled = false;
});
document.addEventListener("click", async (e) => {
  const c = e.target.closest("[data-copy]");
  if (!c) return;
  try { await navigator.clipboard.writeText(c.dataset.copy); const t = c.innerHTML; c.innerHTML = `${icon("check")}Copied`; setTimeout(() => (c.innerHTML = t), 1400); } catch {}
});

async function start() {
  show(true);
  await refresh();
  loadAdProducts(); refreshAds();
  if (token) { clearInterval(timer); timer = setInterval(() => { refresh(); refreshAds(); }, 5000); }   // new orders and clicks appear live
}
if (token) start(); else show(false);
