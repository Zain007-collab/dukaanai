# DukaanAI · AI storefront for small clothing sellers

**Track 1 · ShopBot** · Group 22 · AI-4016 Agentic AI Hackathon

Instagram and WhatsApp clothing sellers in Islamabad–Rawalpindi spend hours a day answering
*"price?"*, *"size available?"*, *"delivery?"* by hand. Late replies lose sales, and nobody suggests the
matching dupatta. **DukaanAI** gives a seller a store page with an AI sales assistant that answers in
English or Roman Urdu, finds in-stock items, suggests one add-on, takes cash-on-delivery orders, and
sends big orders and big discount requests to the seller for approval.

> *"shaadi ke liye kuch chahiye, 5000 tak, M size"* → 2 wedding suits in stock in M → a matching
> dupatta suggested → order confirmed → it appears live on the seller dashboard.

| | |
|---|---|
| **Live website** | `https://<your-app>.vercel.app` (store) · `/seller.html` (seller dashboard) |
| **Agent API base URL** | `https://<your-app>.vercel.app` (`POST /chat`, `GET /health`) |
| **Model** | `claude-haiku-5-5` (thinking off, effort `low`) |
| **Stack** | LangGraph + LangChain · FastAPI · Neon Postgres · Vercel |
| **Demo video** | _link_ |

![Demo](docs/demo.gif)

---

## Architecture

```mermaid
flowchart LR
    subgraph Vercel
      W[Store page<br/>public/index.html] -->|POST /chat| API
      D[Seller dashboard<br/>public/seller.html] -->|/api/admin/*| API
      API[FastAPI<br/>api/index.py → shopbot/main.py]
    end
    API --> G
    subgraph G[LangGraph graph]
      direction TB
      S((START)) --> GU[guard<br/>code: injection + off-topic]
      GU -->|refused| E((END))
      GU --> M[memory<br/>code: save size / name / city]
      M --> A[sales_agent<br/>create_agent + Claude Haiku 5.5]
      A <--> T[[11 tools]]
      A --> E
    end
    G <-->|checkpointer: short-term| N[(Neon Postgres)]
    G <-->|store: long-term| N
    T <-->|products, orders| N
    A <-->|Messages API| C[Claude Haiku 5.5]
```

**Nodes**

| Node | What it does | Model call? |
|---|---|---|
| `guard` | Regex rules refuse prompt injection, requests for other people's data and clearly off-topic requests; logs a flag for the dashboard and ends the turn | No |
| `memory` | Extracts lasting facts from the message (size, shoe size, name, city) and writes them to the long-term store | No |
| `sales_agent` | `create_agent` with Claude Haiku 5.5, the 11 tools and middleware (dynamic prompt with the shopper's memories, history trimming, model and tool call limits) | Yes |

**Tools** (all read the shopper and seller from the request context, never from model arguments)

| Tool | Does |
|---|---|
| `search_catalog(query, max_price, size, colour, category)` | In-stock matches; Roman Urdu synonyms (shaadi → wedding, laal → red, joota → shoes) |
| `check_stock(sku, size)` | Stock per size; suggests in-stock alternatives when a size is out |
| `suggest_matching(sku)` | Upsell: the seller's "goes with" items that are in stock |
| `delivery_quote(city)` | Fee and days per city, free delivery from Rs 10,000 |
| `add_to_cart`, `remove_from_cart`, `view_cart` | The cart lives in the conversation state |
| `apply_discount(percent, code)` | Promo codes and ≤ 10 % apply; above 10 % goes to the seller |
| `place_order(city, …)` | First call returns a summary; places the order only after the shopper says yes |
| `my_orders()` | This shopper's own orders and their status |
| `remember_preference(kind, value)` | Saves a lasting preference to long-term memory |

Prices, totals, stock and discounts are always computed in code. The model never writes a price itself.

---

## Agent API

Open, no login, exactly as required:

```bash
curl https://<your-app>.vercel.app/health
# ok

curl -X POST https://<your-app>.vercel.app/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ayesha", "thread_id": "t1", "message": "Red suit under 4000, size M"}'
# {"reply": "...", "tool_calls": [{"name": "search_catalog", "args": {...}}], "tokens": {"in": 0, "out": 0}}
```

`tool_calls` lists every tool the agent called during that turn. `tokens` is the sum of input and
output tokens over all model calls in the turn (0 when the guard answers without the model).
An optional `seller_id` field picks the store; it defaults to the demo store.

---

## Memory design

| | Short-term memory | Long-term memory |
|---|---|---|
| **What** | The conversation: messages, tool calls, the **cart**, a pending discount, whether an order is waiting for "yes" | Lasting facts about a shopper: name, size, shoe size, favourite colours, budget, style, city |
| **Not stored** | — | Raw chat logs, payment details, abandoned carts |
| **Where** | LangGraph `PostgresSaver` checkpointer in Neon | LangGraph `PostgresStore` in Neon (orders live in the `orders` table, also Neon) |
| **Key** | `thread_id = seller_id:user_id:thread_id` | namespace `("shoppers", seller_id, user_id)` |
| **Written by** | Every graph step, automatically | The `memory` node (code, every message) and the `remember_preference` tool (model) |
| **Read by** | The agent on every turn (last 24 messages are sent to the model, to cap cost) | Code: the dynamic system prompt always includes the shopper's facts |

Nothing is kept in server memory, so a restart or a new serverless instance loses nothing.

**How users are kept separate**

1. **Identity comes from the request, never from the chat.** `user_id` and `seller_id` go into the
   LangGraph runtime context. No tool takes a user or order owner as an argument, so the model has nothing
   it could be talked into changing.
2. **The checkpoint key includes the user.** Two users sending the same `thread_id` get two different
   conversations.
3. **Every database query is filtered by `seller_id` and `user_id`** from the context. `my_orders` can only
   ever return the caller's own orders.
4. **Long-term memory is namespaced per (seller, user).**
5. Requests that ask for other people's data are refused by the guard before the model runs.

---

## Safety

Mapped to the [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/):

| Risk | Our guard |
|---|---|
| **LLM01 Prompt Injection** | The `guard` node (code) refuses "ignore your rules", "you are now…", "show the system prompt", "show other customers' orders" before any model call. The system prompt also tells the model to refuse rule changes. Even if both are bypassed, tools can only see the caller's data. |
| **LLM06 Excessive Agency** | The agent can't do anything irreversible on its own. `place_order` refuses to place an order until the shopper explicitly confirms the summary (checked in code). Discounts above 10 % and orders above Rs 15,000 are created as `awaiting_seller` and need **Approve / Reject** on the seller dashboard. |
| Invented products or prices | Prices, stock, totals and delivery fees come only from tools. The model is told never to quote numbers it didn't get from a tool. |
| Off-topic use | Guard rules for clear cases (homework, code, politics, medical or legal advice), plus the system prompt for the rest. Both steer back to shopping. |
| Cost abuse | Messages over 1,500 characters are refused; at most 6 model calls and 10 tool calls per turn; only recent history is sent to the model. |

Every refused request is logged and shown under **Flagged requests** on the dashboard.

---

## Benchmark

`tests.json` holds our 10 test cases (input + expected behaviour). `benchmark.py` sends them, plus 5
attack tests, to a live API and checks each reply automatically.

```bash
python benchmark.py https://<your-app>.vercel.app
```

<!-- BENCHMARK:START -->
_Results are filled in after the final run against the deployed API._
<!-- BENCHMARK:END -->

Offline tests (no API key, no cost) cover the rules, the order flow, memory and isolation with a scripted
model: `pytest` (26 tests).

---

## Setup

Requires Python 3.12.

```bash
git clone https://github.com/Zain007-collab/dukaanai.git && cd dukaanai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then fill in the values
```

| Variable | Needed for |
|---|---|
| `ANTHROPIC_API_KEY` | The agent (Claude Haiku 5.5) |
| `DATABASE_URL` | Neon Postgres (pooled connection string). Empty = local SQLite + in-memory memory |
| `ADMIN_TOKEN` | Password for the seller dashboard |
| `LLM_PROVIDER`, `GOOGLE_API_KEY` | Optional, local testing only: `LLM_PROVIDER=gemini` runs the same agent on Gemini |

```bash
uvicorn shopbot.main:app --reload --port 8000   # store on http://localhost:8000, dashboard at /seller.html
pytest                                           # offline tests
python benchmark.py http://localhost:8000        # live benchmark
```

**Deploy (free):** import the GitHub repo on Vercel (Framework preset: Other), add `ANTHROPIC_API_KEY`,
`DATABASE_URL` and `ADMIN_TOKEN` as environment variables, deploy. `vercel.json` routes `/chat`,
`/health` and `/api/*` to the Python function; `public/` is served as the website. Tables are created on
first request. Create the Neon project in AWS US East 1, next to Vercel's default function region.

---

## Repository layout

```
api/index.py          Vercel entry point
shopbot/main.py       FastAPI: /chat, /health, store and dashboard APIs
shopbot/graph.py      LangGraph graph, system prompt, middleware, model
shopbot/tools.py      the 11 tools, cart state, order and discount rules
shopbot/guard.py      injection / off-topic rules
shopbot/memory.py     long-term memory extraction and recall
shopbot/catalog.py    demo catalog (20 items) and search
shopbot/db.py         Postgres (Neon) / SQLite data layer
public/               store page and seller dashboard (static, no build step)
tests.json            our 10 test cases · benchmark.py runs them
tests/                offline tests
```

## Business model

Monthly fee per seller, tiered by orders handled (about PKR 3–8k / month; free tier up to 20 orders).
Model cost is tiny: a typical shopping turn on Claude Haiku 5.5 uses about 2–5k tokens, roughly
Rs 0.1–0.2 per turn.
