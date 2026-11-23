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
  $("msgs").innerHTML = ""; bubble(note, "note"); greet();
}

// ── products ──
let products = [];
let filter = "all";

function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]); }
const rs = (n) => "Rs " + Number(n).toLocaleString("en-PK");

const CAT_ICON = { suit: "shirt", kurta: "shirt", dupatta: "layers", shawl: "layers", shoes: "shoe" };

function renderGrid() {
  const list = products.filter((p) => filter === "all" || p.category === filter || p.tags.includes(filter));
  $("count").textContent = `${list.length} ${list.length === 1 ? "piece" : "pieces"}`;
  $("grid").innerHTML = list.map((p) => {
    const sizes = Object.entries(p.stock).map(([s, n]) => `<span class="size ${n > 0 ? "" : "out"}" title="${n > 0 ? n + " in stock" : "Sold out"}">${esc(s)}</span>`).join("");
    const left = Object.values(p.stock).reduce((a, b) => a + b, 0);
    const flag = left === 0 ? "Sold out" : left <= 2 ? `Only ${left} left` : "";
    return `<article class="card">
      <div class="swatch" data-cat="${esc(p.category)}" style="--c:${COLOURS[p.colour] || "#b9aea4"}">
        <span class="sku">${esc(p.sku)}</span>${flag ? `<span class="stock-flag">${flag}</span>` : ""}
        <span class="cat">${icon(CAT_ICON[p.category] || "bag")}${esc(p.category)}</span>
      </div>
      <div class="body">
        <h3>${esc(p.name)}</h3>
        <div class="fabric">${esc(p.fabric)}, ${esc(p.colour)}</div>
        <div class="sizes">${sizes}</div>
        <div class="foot">
          <span class="price">${rs(p.price)}</span>
          <button class="btn small ask" data-sku="${esc(p.sku)}">${icon("sparkles")}Ask Noor</button>
        </div>
      </div></article>`;
  }).join("") || `<p class="empty">${icon("inbox")}Nothing in this filter right now.</p>`;
}

const CATEGORIES = ["all", "suit", "kurta", "dupatta", "shoes", "shawl"];
const OCCASIONS = ["wedding", "eid", "men"];
const LABELS = { all: "All", suit: "Suits", kurta: "Kurtas", dupatta: "Dupattas", shoes: "Shoes", shawl: "Shawls",
  wedding: "Wedding", eid: "Eid", men: "Men" };
function renderFilters() {
  const chip = (n) => `<button class="chip ${n === filter ? "on" : ""}" data-f="${n}" aria-pressed="${n === filter}">${LABELS[n]}</button>`;
  $("filters").innerHTML = `<span class="group-label">Category</span>${CATEGORIES.map(chip).join("")}`
    + `<span class="sep"></span><span class="group-label">Occasion</span>${OCCASIONS.map(chip).join("")}`;
}
$("filters").addEventListener("click", (e) => {
  const b = e.target.closest("[data-f]");
  if (!b) return;
  filter = b.dataset.f; renderFilters(); renderGrid();
});
$("grid").addEventListener("click", (e) => {
  const b = e.target.closest("[data-sku]");
  if (b) send(`Tell me about ${b.dataset.sku}. Which sizes are available?`);
});

async function loadProducts() {
  try {
    const [shop, list] = await Promise.all([fetch(`${API}/api/shop`).then((r) => r.json()), fetch(`${API}/api/products`).then((r) => r.json())]);
    $("shopName").textContent = `${shop.name}, ${shop.city}`;
    if (shop.free_delivery_from) $("freeDelivery").textContent = `Free delivery from ${rs(shop.free_delivery_from)}`;
    products = list; renderFilters(); renderGrid();
  } catch {
    $("grid").innerHTML = `<p class="empty">${icon("alert")}The collection didn't load. Refresh the page to try again.</p>`;
  }
}

// ── chat ──
function bubble(text, who) {
  const el = document.createElement("div");
  el.className = `msg ${who}`;
  el.innerHTML = esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");   // escape first, then **bold**
  $("msgs").appendChild(el);
  $("msgs").scrollTop = $("msgs").scrollHeight;
  return el;
}
function meta(data, ms) {
  const el = document.createElement("div");
  el.className = "meta";
  const tools = (data.tool_calls || []).map((t) => `<span class="tool">${icon("wrench")}${esc(t.name)}</span>`).join("");
  const blocked = !(data.tool_calls || []).length && !(data.tokens.in + data.tokens.out);
  el.innerHTML = `${tools}${blocked ? `<span class="tool">${icon("shield")}guard</span>` : ""}`
    + `<span class="stat">${icon("zap")}${(data.tokens.in + data.tokens.out).toLocaleString()} tokens</span>`
    + `<span class="stat">${icon("clock")}${(ms / 1000).toFixed(1)}s</span>`;
  $("msgs").appendChild(el);
  $("msgs").scrollTop = $("msgs").scrollHeight;
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
  typing.className = "typing"; typing.setAttribute("aria-label", "Noor is typing");
  typing.innerHTML = "<span></span><span></span><span></span>";
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
    bubble("I couldn't reach the shop. Check your connection and send the message again.", "bot");
  } finally {
    busy = false;
  }
}
$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("input").value); });
$("suggest").innerHTML = SUGGESTIONS.map((s) => `<button class="chip" type="button" data-say="${esc(s)}">${icon("sparkles")}${esc(s)}</button>`).join("");
$("suggest").addEventListener("click", (e) => { const b = e.target.closest("[data-say]"); if (b) send(b.dataset.say); });

greet();
loadProducts();
