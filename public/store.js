// Store page: product grid + chat with the DukaanAI agent (POST /chat).
const API = window.DUKAAN_API || "";
const $ = (id) => document.getElementById(id);

const COLOURS = {
  red: "#c0392b", maroon: "#7b1e2b", green: "#1f7a4d", black: "#2b2b2b", pink: "#e58fb0", yellow: "#f2c335",
  blue: "#1f3a6b", white: "#f1ece2", peach: "#f4b393", gold: "#c99a3b", multi: "#9b7ad6", brown: "#7a4a2a",
  beige: "#d9c7a8",
};
const SUGGESTIONS = [
  "shaadi ke liye kuch chahiye, 5000 tak, M size",
  "Red suit under 4000, size M",
  "Do you have SKU-17 in XL?",
  "Delivery to Lahore?",
  "Mera size M hai, yaad rakhna",
  "Show my orders",
];

// ── who is shopping: a shopper ID kept in this browser, plus one thread per conversation ──
function store(key, value) {
  try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch { return null; }
}
const rid = () => Math.random().toString(36).slice(2, 8);
let userId = store("dukaan.user") || `shopper-${rid()}`;
let threadId = store("dukaan.thread") || `t-${rid()}`;
store("dukaan.user", userId); store("dukaan.thread", threadId);
$("userId").value = userId;
$("userId").addEventListener("change", (e) => {
  userId = e.target.value.trim() || `shopper-${rid()}`;
  e.target.value = userId; store("dukaan.user", userId);
  newThread("Switched shopper. Each shopper has their own chats, orders and memory.");
});
$("newChat").addEventListener("click", () => newThread("New conversation. I still remember your preferences from earlier chats."));

function newThread(note) {
  threadId = `t-${rid()}`; store("dukaan.thread", threadId);
  $("msgs").innerHTML = ""; greet(note);
}

// ── products ──
let products = [];
let filter = "all";

function swatch(p) {
  const c = COLOURS[p.colour] || "#b9aea4";
  return `linear-gradient(135deg, ${c} 0%, ${c}cc 55%, #ffffff55 100%)`;
}
function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]); }
const rs = (n) => "Rs " + Number(n).toLocaleString("en-PK");

function renderGrid() {
  const list = products.filter((p) => filter === "all" || p.category === filter || p.tags.includes(filter));
  $("grid").innerHTML = list.map((p) => {
    const sizes = Object.entries(p.stock).map(([s, n]) => `<span class="size ${n > 0 ? "" : "out"}">${esc(s)}</span>`).join("");
    return `<article class="card">
      <div class="swatch" style="background:${swatch(p)}"><span class="sku">${esc(p.sku)}</span><span class="cat">${esc(p.category)}</span></div>
      <div class="body">
        <h3>${esc(p.name)}</h3>
        <div class="price">${rs(p.price)}</div>
        <div class="sizes">${sizes}</div>
        <div class="muted">${esc(p.fabric)} · ${esc(p.tags.join(", "))}</div>
        <button class="btn small ask" data-sku="${esc(p.sku)}">Ask about this</button>
      </div></article>`;
  }).join("") || `<p class="empty">Nothing here yet.</p>`;
}

function renderFilters() {
  const names = ["all", "suit", "kurta", "dupatta", "shoes", "shawl", "wedding", "eid", "men"];
  $("filters").innerHTML = names.map((n) => `<button class="chip ${n === filter ? "on" : ""}" data-f="${n}">${n === "all" ? "All" : n[0].toUpperCase() + n.slice(1)}</button>`).join("");
}
$("filters").addEventListener("click", (e) => {
  if (!e.target.dataset.f) return;
  filter = e.target.dataset.f; renderFilters(); renderGrid();
});
$("grid").addEventListener("click", (e) => {
  const sku = e.target.dataset.sku;
  if (sku) send(`Tell me about ${sku}. Which sizes are available?`);
});

async function loadProducts() {
  try {
    const [shop, list] = await Promise.all([fetch(`${API}/api/shop`).then((r) => r.json()), fetch(`${API}/api/products`).then((r) => r.json())]);
    $("shopName").textContent = `${shop.name} · ${shop.city}`;
    products = list; renderFilters(); renderGrid();
  } catch {
    $("grid").innerHTML = `<p class="empty">Couldn't load the collection. Please refresh.</p>`;
  }
}

// ── chat ──
function bubble(text, who) {
  const el = document.createElement("div");
  el.className = `msg ${who}`;
  el.textContent = text;
  $("msgs").appendChild(el);
  $("msgs").scrollTop = $("msgs").scrollHeight;
  return el;
}
function meta(data, ms) {
  const el = document.createElement("div");
  el.className = "meta";
  const tools = (data.tool_calls || []).map((t) => `<span class="tool">${esc(t.name)}</span>`).join("");
  el.innerHTML = `${tools}<span>${data.tokens.in + data.tokens.out} tokens · ${(ms / 1000).toFixed(1)}s</span>`;
  $("msgs").appendChild(el);
}
function greet(note) {
  bubble(note || "Assalam-o-alaikum! I'm Noor. Tell me what you're shopping for (occasion, budget, size) and I'll find it in stock. Aap Roman Urdu mein bhi pooch sakte hain.", "bot");
}

let busy = false;
async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  bubble(text, "me");
  $("input").value = "";
  const typing = document.createElement("div");
  typing.className = "typing"; typing.textContent = "Noor is typing…";
  $("msgs").appendChild(typing);
  const t0 = performance.now();
  try {
    const r = await fetch(`${API}/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, thread_id: threadId, message: text }),
    });
    const data = await r.json();
    typing.remove();
    bubble(data.reply || "Sorry, something went wrong.", "bot");
    if (data.tokens) meta(data, performance.now() - t0);
    if ((data.tool_calls || []).some((t) => t.name === "place_order")) loadProducts();   // stock changed
  } catch {
    typing.remove();
    bubble("I couldn't reach the shop right now. Please try again in a moment.", "bot");
  } finally {
    busy = false;
  }
}
$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("input").value); });
$("suggest").innerHTML = SUGGESTIONS.map((s) => `<button class="chip" type="button">${esc(s)}</button>`).join("");
$("suggest").addEventListener("click", (e) => { if (e.target.matches(".chip")) send(e.target.textContent); });

greet();
loadProducts();
