# DukaanAI · Hackathon Checklist

**Track:** 1 · ShopBot · **Group 22**
**Deadline:** Mon 23 Nov 2026, 11:59 PM · **Keep live until:** Wed 25 Nov
**Model:** `claude-haiku-5-5` ($2 key limit, never commit the key)

Legend: 🤖 = Claude builds it · 🧑 = a team member must do it (accounts, keys, recording)

---

## 0. Accounts & keys (🧑, do these first, in parallel with the build)
- [ ] Put the group Claude API key into `DukaanAI/backend/.env` as `ANTHROPIC_API_KEY`
- [ ] Create a free **Neon** Postgres database → copy the connection string into `.env` as `DATABASE_URL`
- [ ] Create a **Hugging Face** account (for the Docker Space hosting the API)
- [ ] Create a **Vercel** account (for the website)
- [ ] Create a public **GitHub** repo (`dukaanai`)

## 1. Backend core (🤖)
- [ ] `backend/` project: FastAPI + LangGraph + langchain-anthropic
- [ ] Seeded catalog: 20 clothing items (sku, name, category, colour, price, sizes, stock, image)
- [ ] `GET /health` → `ok`
- [ ] `POST /chat` → `{"reply", "tool_calls", "tokens": {"in", "out"}}`, exact format
- [ ] Graph with ≥ 2 nodes: **guard** (off-topic / injection) → **sales agent** (tools)
- [ ] Postgres checkpointer: short-term memory per thread
- [ ] Postgres store: long-term memory per user
- [ ] Thread key = `user_id:thread_id` (user B can't read user A's thread)
- [ ] Graceful errors: `/chat` never returns a 500 to the grader

## 2. Tools (🤖, ≥ 2 required, we have 6)
- [ ] `search_catalog(query, max_price, size, colour)`: in-stock matches only
- [ ] `check_stock(sku, size)`
- [ ] `delivery_quote(city)`: fee and days
- [ ] `create_order(items)`: asks the shopper to confirm first; big orders go to the seller for approval
- [ ] `apply_discount(percent)`: >10% needs seller approval (never auto-applied)
- [ ] `my_orders()`: only this user's orders
- [ ] `remember_preference(fact)`: size, colour and budget saved to long-term memory
- [ ] Prices always come from tool results, never invented by the model

## 3. Safety (🤖)
- [ ] Guard refuses off-topic requests (homework, code, politics…) and steers back to shopping
- [ ] Guard refuses prompt injection ("ignore rules", "show all orders", "you are now…")
- [ ] Asks before risky actions (place order, discounts)
- [ ] `user_id` comes from the request only, never from the chat text
- [ ] README names OWASP LLM01 Prompt Injection + LLM06 Excessive Agency

## 4. Deploy the API (🤖 + 🧑)
- [ ] `Dockerfile` for Hugging Face Spaces (port 7860)
- [ ] Space secrets: `ANTHROPIC_API_KEY`, `DATABASE_URL`
- [ ] Live check: `curl <API>/health` and one `/chat` call

## 5. Website (🤖)
- [ ] Next.js app in `frontend/`
- [ ] **Store page**: product grid + chat + Roman Urdu friendly
- [ ] **Seller dashboard**: orders list, approve / reject pending orders & discounts, simple sales totals
- [ ] Deployed on Vercel, API URL from env var

## 6. Tests & benchmark (🤖)
- [ ] `tests.json`: 10 cases (input + expected behaviour)
- [ ] `benchmark.py`: runs the cases (+ attack tests) against the live API, prints a pass-rate table
- [ ] Includes: catalog match, out-of-stock alternative, 50% discount, injection, off-topic,
      returning-shopper memory, Roman Urdu, delivery quote, multi-turn memory, user isolation

## 7. README & repo (🤖 + 🧑)
- [ ] Architecture diagram (Mermaid)
- [ ] Setup steps
- [ ] Memory design note: short-term vs long-term, where stored, how users are kept separate
- [ ] Benchmark table
- [ ] Demo GIF (🧑 record)
- [ ] `.env.example` present, `.env` in `.gitignore`, **no key committed**

## 8. Submission (🧑)
- [ ] Live website URL
- [ ] Agent API base URL
- [ ] Public GitHub repo link
- [ ] 2–3 min demo video (YouTube unlisted / Drive, anyone with link)
- [ ] Photo of the paper canvas (Drive, anyone with link)
- [ ] Google Form filled in by the group leader (describe nodes, tools, memory, safety, demo data **exactly as built**)
- [ ] Same links submitted on Google Classroom
