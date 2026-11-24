"""DukaanAI API.

Graded endpoints (open, no login):
    GET  /health  -> ok
    POST /chat    {"user_id", "thread_id", "message"} -> {"reply", "tool_calls", "tokens": {"in", "out"}}

Every route is also served under /api/... for the website. Seller dashboard routes need X-Admin-Token.
"""
import csv
import io
import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from langchain.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from shopbot import catalog, db
from shopbot.config import (ADMIN_TOKEN, AUTO_DISCOUNT_CAP, DEFAULT_SELLER, FREE_DELIVERY_FROM,
                            ORDER_APPROVAL_LIMIT, PRICE_IN_PER_M, PRICE_OUT_PER_M, ROOT, SELLERS)
from shopbot.graph import build_graph
from shopbot.tools import ShopContext

log = logging.getLogger("dukaanai")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DukaanAI", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_graph = None
_graph_lock = threading.Lock()


def graph():
    """Build the graph once per process (lazily, so /health never touches the DB or the model)."""
    global _graph
    with _graph_lock:
        if _graph is None:
            db.init_db()
            if db.IS_PG:
                from langgraph.checkpoint.postgres import PostgresSaver
                from langgraph.store.postgres import PostgresStore
                saver, store = PostgresSaver(db.pool()), PostgresStore(db.pool())
                for part in (saver, store):
                    try:
                        part.setup()   # idempotent migrations
                    except Exception as e:   # a parallel cold start may race us; tables exist anyway
                        log.warning("setup skipped: %s", e)
            else:
                from langgraph.checkpoint.memory import InMemorySaver
                from langgraph.store.memory import InMemoryStore
                log.warning("DATABASE_URL not set: using in-memory checkpointer and store (local dev only)")
                saver, store = InMemorySaver(), InMemoryStore()
            _graph = build_graph(saver, store)
    return _graph


router = APIRouter()


# ───────────────────────── graded API ─────────────────────────

class ChatIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8000)
    seller_id: str = DEFAULT_SELLER   # optional: which store. Defaults to the demo store.


class ChatOut(BaseModel):
    reply: str
    tool_calls: list[dict]
    tokens: dict


@router.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    started = time.time()
    seller = body.seller_id if body.seller_id in SELLERS else DEFAULT_SELLER
    ctx = ShopContext(user_id=body.user_id.strip(), seller_id=seller, thread_id=body.thread_id.strip())
    # CUSTOM: the checkpoint key includes the user, so one user can never open another user's thread
    config = {"configurable": {"thread_id": f"{seller}:{ctx.user_id}:{ctx.thread_id}"}}
    try:
        result = graph().invoke({"messages": [HumanMessage(body.message)]}, config, context=ctx)
        messages = result["messages"]
        start = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage)) + 1
        new = [m for m in messages[start:] if isinstance(m, AIMessage)]
        reply = next((m.text for m in reversed(new) if m.text.strip()), "")
        calls = [{"name": c["name"], "args": c["args"]} for m in new for c in m.tool_calls]
        t_in = sum((m.usage_metadata or {}).get("input_tokens", 0) for m in new)
        t_out = sum((m.usage_metadata or {}).get("output_tokens", 0) for m in new)
        blocked = any(m.name == "guard" for m in new)
        if not reply:
            reply = "Sorry, I couldn't finish that. Could you say it another way?"
    except Exception:
        log.exception("chat failed")
        reply, calls, t_in, t_out, blocked = ("Sorry, something went wrong on our side. Please try again.",
                                              [], 0, 0, False)
    try:
        db.log_usage({"id": uuid4().hex, "seller_id": seller, "user_id": ctx.user_id, "tokens_in": t_in,
                      "tokens_out": t_out, "tool_calls": len(calls),
                      "latency_ms": int((time.time() - started) * 1000), "blocked": int(blocked)})
    except Exception:
        log.exception("usage log failed")
    return ChatOut(reply=reply, tool_calls=calls, tokens={"in": t_in, "out": t_out})


# ───────────────────────── store page ─────────────────────────

@router.get("/api/shop")
def shop(seller_id: str = DEFAULT_SELLER):
    seller = SELLERS.get(seller_id) or SELLERS[DEFAULT_SELLER]
    return {"seller_id": seller_id, "name": seller["name"], "city": seller["city"],
            "free_delivery_from": FREE_DELIVERY_FROM, "approval_limit": ORDER_APPROVAL_LIMIT,
            "auto_discount_cap": AUTO_DISCOUNT_CAP}


@router.get("/api/products")
def products(seller_id: str = DEFAULT_SELLER):
    db.init_db()
    return [{k: p[k] for k in ("sku", "name", "category", "colour", "price", "stock", "tags", "fabric",
                               "description")} for p in db.products(seller_id)]


# ───────────────────────── seller dashboard ─────────────────────────

def require_admin(token: str | None):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Wrong dashboard password")


@router.get("/api/admin/summary")
def summary(seller_id: str = DEFAULT_SELLER, x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    db.init_db()
    orders = db.orders_for_seller(seller_id)
    usage = db.usage_totals(seller_id)
    by_status = defaultdict(int)
    daily = defaultdict(int)
    for o in orders:
        by_status[o["status"]] += 1
        if o["status"] == "confirmed":
            daily[o["created_at"][:10]] += o["total"]
    cost = usage["tokens_in"] / 1e6 * PRICE_IN_PER_M + usage["tokens_out"] / 1e6 * PRICE_OUT_PER_M
    return {
        "orders": len(orders), "by_status": by_status,
        "revenue": sum(o["total"] for o in orders if o["status"] == "confirmed"),
        "daily_sales": [{"day": d, "total": daily[d]} for d in sorted(daily)][-14:],
        "chats": usage["chats"], "tokens_in": usage["tokens_in"], "tokens_out": usage["tokens_out"],
        "est_cost_usd": round(cost, 4), "avg_latency_ms": usage["avg_latency_ms"],
        "flags": len(db.flags(seller_id, limit=1000)),
        "low_stock": [{"sku": p["sku"], "name": p["name"], "stock": p["stock"]} for p in db.products(seller_id)
                      if sum(p["stock"].values()) <= 2],
    }


@router.get("/api/admin/orders")
def admin_orders(seller_id: str = DEFAULT_SELLER, status: str | None = None,
                 x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    return db.orders_for_seller(seller_id, status)


def _restore_stock(seller_id: str, o: dict):
    for i in o["items"]:
        p = db.product(seller_id, i["sku"])
        if p:
            db.set_stock(seller_id, i["sku"], {**p["stock"], i["size"]: p["stock"].get(i["size"], 0) + i["qty"]})


@router.post("/api/admin/orders/{order_id}/{action}")
def decide(order_id: str, action: str, seller_id: str = DEFAULT_SELLER,
           x_admin_token: str | None = Header(None)):
    """The seller's approval step: approve (applies any requested discount) or reject (restocks)."""
    require_admin(x_admin_token)
    o = db.order(seller_id, order_id)
    if not o:
        raise HTTPException(404, "No such order")
    if o["status"] != "awaiting_seller":
        raise HTTPException(409, f"Order is already {o['status']}")
    if action == "approve":
        total = o["total"]
        if o["discount_status"] == "pending_seller":
            total = o["subtotal"] - o["subtotal"] * o["discount_percent"] // 100 + o["delivery_fee"]
        db.update_order(seller_id, order_id, status="confirmed", total=total,
                        discount_status="approved" if o["discount_status"] == "pending_seller" else o["discount_status"])
    elif action == "reject":
        db.update_order(seller_id, order_id, status="rejected")
        _restore_stock(seller_id, o)
    else:
        raise HTTPException(400, "action must be approve or reject")
    return db.order(seller_id, order_id)


@router.get("/api/admin/flags")
def admin_flags(seller_id: str = DEFAULT_SELLER, x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    return db.flags(seller_id)


class CsvIn(BaseModel):
    csv: str = Field(max_length=200_000)


@router.post("/api/admin/products/csv")
def upload_csv(body: CsvIn, seller_id: str = DEFAULT_SELLER, x_admin_token: str | None = Header(None)):
    """Upsert products from CSV: sku,name,category,colour,price,stock,tags,fabric,matches,description
    where stock is like 'S:2;M:3' and tags/matches are ';'-separated."""
    require_admin(x_admin_token)
    db.init_db()
    count = 0
    for row in csv.DictReader(io.StringIO(body.csv.strip())):
        try:
            stock = {k.strip(): int(v) for k, v in (part.split(":") for part in row["stock"].split(";") if part)}
            db.upsert_product(seller_id, {
                "sku": row["sku"].strip().upper(), "name": row["name"].strip(), "category": row["category"].strip().lower(),
                "colour": row["colour"].strip().lower(), "price": int(row["price"]), "stock": stock,
                "tags": [t.strip().lower() for t in row.get("tags", "").split(";") if t.strip()],
                "fabric": row.get("fabric", "").strip(), "description": row.get("description", "").strip(),
                "matches": [m.strip().upper() for m in row.get("matches", "").split(";") if m.strip()]})
            count += 1
        except (KeyError, ValueError) as e:
            raise HTTPException(400, f"Bad row {row}: {e}")
    return {"upserted": count}


app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)   # /api/chat, /api/health too

try:   # Bonus: AdForge (Track 2) integration. Isolated: if it fails to load, the graded API keeps working.
    from shopbot.adforge import router as adforge_router
    app.include_router(adforge_router)
except Exception:
    log.exception("AdForge integration disabled")

# Local dev: serve the website from the same server. On Vercel, public/ is served by the CDN.
_public = ROOT / "public"
if _public.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_public, html=True), name="site")
