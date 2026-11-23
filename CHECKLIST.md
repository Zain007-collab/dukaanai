# DukaanAI · Hackathon Checklist

**Track:** 1 · ShopBot · **Group 22**
**Deadline:** Mon 23 Nov 2026, 11:59 PM · **Keep live until:** Wed 25 Nov
**Model:** `claude-haiku-5-5` ($2 key limit, never commit the key)
**Repo:** https://github.com/Zain007-collab/dukaanai

Legend: 🤖 = Claude builds it · 🧑 = a team member must do it (accounts, keys, recording)

---

## 0. Accounts & keys (🧑)
- [x] Group Claude API key in `.env` as `ANTHROPIC_API_KEY`
- [x] Gemini key in `.env` as `GOOGLE_API_KEY` (local testing only, `LLM_PROVIDER=gemini`)
- [x] **Neon** Postgres project (AWS US East 1, pooled string) → `DATABASE_URL` in `.env`
- [x] Public **GitHub** repo `dukaanai` (commits as Zain007-collab only)
- [x] **Vercel** project `dukaanai` (Hobby), hosts both the website and the API

## 1. Backend core (🤖)
- [x] FastAPI + LangGraph + langchain-anthropic (`shopbot/`)
- [x] Seeded catalog: 20 clothing items (sku, name, category, colour, price, stock per size, tags, matches)
- [x] `GET /health` → `ok`
- [x] `POST /chat` → `{"reply", "tool_calls", "tokens": {"in", "out"}}`, exact format
- [x] Graph with 3 nodes: **guard** → **memory** → **sales_agent**
- [x] Postgres checkpointer (short-term memory per thread): tables created in Neon
- [x] Postgres store (long-term memory per user): tables created in Neon
- [x] Thread key = `seller_id:user_id:thread_id` (user B can't read user A's thread)
- [x] Graceful errors: `/chat` never returns a 500 to the grader
- [x] Gemini / Claude switch for local testing (production always Claude)

## 2. Tools (🤖, ≥ 2 required, we have 11)
- [x] `search_catalog` (in-stock only, Roman Urdu synonyms)
- [x] `check_stock` (suggests alternatives when out of stock)
- [x] `suggest_matching` (upsell)
- [x] `delivery_quote`
- [x] `add_to_cart` / `remove_from_cart` / `view_cart` (cart in conversation state)
- [x] `apply_discount`: ≤ 10% applied, > 10% sent to the seller
- [x] `place_order`: summary first, places only after an explicit "yes"; big orders wait for the seller
- [x] `my_orders`: only this user's orders
- [x] `remember_preference`: long-term memory
- [x] Prices always come from tool results, never invented by the model

## 3. Safety (🤖)
- [x] Guard refuses off-topic requests (homework, code, politics…) and steers back to shopping
- [x] Guard refuses prompt injection ("ignore rules", "show all orders", "you are now…")
- [x] Asks before risky actions (order confirmation, seller approval for discounts and big orders)
- [x] `user_id` comes from the request only, never from the chat text
- [x] README names OWASP LLM01 Prompt Injection + LLM06 Excessive Agency

## 4. Deploy (🧑 + 🤖)
- [x] `vercel.json` + `api/index.py`: website and API on one Vercel project
- [x] 🧑 Vercel project (preset: Other), env vars `ANTHROPIC_API_KEY`, `DATABASE_URL`, `ADMIN_TOKEN`, deployed with the Vercel CLI (not Git-connected: a push does **not** redeploy)
- [x] 🧑 Live URL: https://dukaanai-one.vercel.app
- [x] 🤖 Live check: `/health`, `/chat`, store page, dashboard, memory survives on Neon

## 5. Website (🤖)
- [x] Static site in `public/` (no build step, no Node needed)
- [x] **Store page**: product grid + filters + chat + Roman Urdu suggestions + shopper ID / new chat
- [x] **Seller dashboard**: KPIs (revenue, chats, tokens, cost, latency), approve / reject, sales chart, orders, flagged requests, low stock, CSV upload
- [ ] 🤖 Check both pages on the live URL (desktop + phone width)

## 6. Tests & benchmark (🤖)
- [x] `tests.json`: 10 cases (input + expected behaviour)
- [x] `benchmark.py`: 10 cases + 5 attack tests against a live API → pass-rate table
- [x] Offline tests: 26 passing (`pytest`, no API cost)
- [x] Local benchmark on Claude: 14/15 (the one failure was the cart bug, since fixed)
- [x] Local benchmark on Gemini: 15/15
- [x] 🤖 Final benchmark on Claude against the **deployed** API: 15/15 → table into README

## 7. README & repo (🤖 + 🧑)
- [x] Architecture diagram (Mermaid)
- [x] Setup steps
- [x] Memory design note: short-term vs long-term, where stored, how users are kept separate
- [x] Safety section (OWASP)
- [x] 🤖 Benchmark table (after final run)
- [x] 🤖 Live website + API URLs
- [ ] 🧑 Demo GIF (save as `docs/demo.gif`)
- [x] `.env.example` present, `.env` in `.gitignore`, **no key committed** (checked)

## 8. Submission (🧑)
- [x] Live website URL: https://dukaanai-one.vercel.app
- [x] Agent API base URL (same as the website URL): https://dukaanai-one.vercel.app
- [x] Public GitHub repo link: https://github.com/Zain007-collab/dukaanai
- [ ] 2–3 min demo video (YouTube unlisted / Drive, anyone with link)
- [ ] Photo of the paper canvas (Drive, anyone with link)
- [ ] Google Form filled in by the group leader (describe nodes, tools, memory, safety, demo data **exactly as built**: see README)
- [ ] Same links submitted on Google Classroom
