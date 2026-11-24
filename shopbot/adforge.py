"""Bonus: AdForge (Track 2) inside ShopBot.

The seller picks a product on the dashboard; a small LangGraph graph writes two Instagram ad variants
(an A/B test), and each variant gets a tracking link. Clicks on the links are counted per variant, so the
seller can read the results and keep the winner.

    brief    code. Loads the product's real facts (price, in-stock sizes, fabric, tags) from the catalog.
    writer   Claude Haiku 5.5 with structured output: two variants with different angles.
    checker  code. Removes any price or discount the model wrote, then adds the real price, sizes and the
             tracking link from the database. The ad can never promise a price or discount the shop doesn't offer.

Kept separate from the shopping agent: nothing here is used by POST /chat or GET /health.
"""
import re
from typing import TypedDict
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from shopbot import catalog, db
from shopbot.config import ADMIN_TOKEN, DEFAULT_SELLER, FREE_DELIVERY_FROM, MODEL, SELLERS

OCCASIONS = ["any", "wedding", "mehndi", "eid", "winter", "everyday"]


class AdVariant(BaseModel):
    angle: str = Field(description="Short name of the creative angle, e.g. 'Wedding guest glow'")
    hook: str = Field(description="First line that stops the scroll. Max 70 characters. No prices, no discounts.")
    caption: str = Field(description="2-4 short lines mixing English and Roman Urdu. Describe the look and the occasion. "
                                     "No prices, no discounts, no stock numbers.")
    hashtags: list[str] = Field(description="5-7 relevant hashtags without spaces")
    cta: str = Field(description="Call to action, e.g. 'DM us or tap the link to order'. No prices.")


class AdSet(BaseModel):
    audience: str = Field(description="One line: who to show these ads to (age, city, interest)")
    variants: list[AdVariant] = Field(description="Exactly two variants with clearly different angles", min_length=2, max_length=2)


class AdState(TypedDict, total=False):
    seller_id: str
    sku: str
    occasion: str
    product: dict
    brief: str
    draft: AdSet
    ads: list[dict]
    audience: str


# ── nodes ──

def brief_node(state: AdState) -> AdState:
    p = db.product(state["seller_id"], state["sku"])
    if not p:
        raise HTTPException(404, f"{state['sku']} is not in the catalog")
    sizes = ", ".join(catalog.in_stock_sizes(p)) or "sold out"
    occ = state.get("occasion") or "any"
    brief = (f"Product: {p['name']} ({p['sku']}), {p['fabric']}, colour {p['colour']}. {p['description']} "
             f"Tags: {', '.join(p['tags'])}. In-stock sizes: {sizes}. Occasion to target: {occ}. "
             f"Shop: {SELLERS.get(state['seller_id'], {}).get('name', 'our shop')}, cash on delivery across Pakistan.")
    return {"product": p, "brief": brief}


WRITER_PROMPT = ("You write Instagram ads for a small Pakistani clothing boutique. Write two ad variants for an A/B "
                 "test, each with a clearly different angle (for example the occasion vs the fabric and craft). "
                 "Mix English and Roman Urdu naturally. Never mention prices, discounts, sales or stock counts: the "
                 "shop adds the real price itself.")


def build_writer():
    return ChatAnthropic(model=MODEL, max_tokens=900, thinking={"type": "disabled"}, effort="low",
                         timeout=40, max_retries=1).with_structured_output(AdSet)


def writer_node(state: AdState) -> AdState:
    draft = build_writer().invoke([("system", WRITER_PROMPT), ("human", state["brief"])])
    return {"draft": draft}


PRICE_OR_DEAL = re.compile(r"(rs\.?\s?\d[\d,]*|\d[\d,]*\s?(rs|rupees|pkr)\b|\d+\s?%|\bsale\b|\bdiscount\w*|\boff\b|\bfree\b)", re.I)


def clean(text: str) -> str:
    """Drop any line where the model wrote a price, a percentage or a deal. Prices come only from the catalog."""
    return "\n".join(line for line in text.splitlines() if not PRICE_OR_DEAL.search(line)).strip()


def checker_node(state: AdState) -> AdState:
    p = state["product"]
    sizes = ", ".join(catalog.in_stock_sizes(p)) or "sold out"
    facts = (f"{catalog.fmt_price(p['price'])} | Sizes: {sizes} | Cash on delivery across Pakistan, "
             f"free delivery from {catalog.fmt_price(FREE_DELIVERY_FROM)}")
    ads = []
    for name, v in zip("AB", state["draft"].variants[:2]):
        tags = " ".join("#" + re.sub(r"[^\w]", "", t.lstrip("#")) for t in v.hashtags[:7] if re.sub(r"[^\w]", "", t))
        code = uuid4().hex[:8]
        body = "\n\n".join(part for part in [clean(v.hook), clean(v.caption), facts, clean(v.cta) or "DM us or tap the link to order.",
                                             tags] if part)
        ads.append({"id": code, "variant": name, "angle": clean(v.angle)[:80] or f"Variant {name}", "text": body})
    return {"ads": ads, "audience": clean(state["draft"].audience)[:200]}


def build_adforge():
    g = StateGraph(AdState)
    g.add_node("brief", brief_node)
    g.add_node("writer", writer_node)
    g.add_node("checker", checker_node)
    g.add_edge(START, "brief")
    g.add_edge("brief", "writer")
    g.add_edge("writer", "checker")
    g.add_edge("checker", END)
    return g.compile()


# ── storage (own table, created on first use, so the shopping agent never depends on it) ──

_table_ready = False


def ensure_table():
    global _table_ready
    if _table_ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS ads (
        id TEXT PRIMARY KEY, batch TEXT NOT NULL, seller_id TEXT NOT NULL, sku TEXT NOT NULL, variant TEXT NOT NULL,
        angle TEXT NOT NULL, audience TEXT NOT NULL, text TEXT NOT NULL, clicks INTEGER NOT NULL, created_at TEXT NOT NULL)""")
    _table_ready = True


# ── API ──

router = APIRouter()


class AdIn(BaseModel):
    sku: str = Field(min_length=1, max_length=20)
    occasion: str = "any"


def _admin(token: str | None):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Wrong dashboard password")


@router.post("/api/admin/ads")
def create_ads(body: AdIn, seller_id: str = DEFAULT_SELLER, x_admin_token: str | None = Header(None)):
    _admin(x_admin_token)
    db.init_db()
    ensure_table()
    occasion = body.occasion if body.occasion in OCCASIONS else "any"
    try:
        out = build_adforge().invoke({"seller_id": seller_id, "sku": body.sku.strip().upper(), "occasion": occasion})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"The ad writer didn't answer. Try again in a moment. ({type(e).__name__})")
    batch, now = uuid4().hex[:6], db.now()
    for a in out["ads"]:
        db.execute("INSERT INTO ads (id, batch, seller_id, sku, variant, angle, audience, text, clicks, created_at)"
                   " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (a["id"], batch, seller_id, out["product"]["sku"], a["variant"], a["angle"], out["audience"], a["text"], 0, now))
    return {"batch": batch, "sku": out["product"]["sku"], "name": out["product"]["name"], "audience": out["audience"],
            "ads": [{**a, "clicks": 0} for a in out["ads"]]}


@router.get("/api/admin/ads")
def list_ads(seller_id: str = DEFAULT_SELLER, x_admin_token: str | None = Header(None)):
    _admin(x_admin_token)
    db.init_db()
    ensure_table()
    return db.query("SELECT * FROM ads WHERE seller_id = ? ORDER BY created_at DESC, variant LIMIT 40", (seller_id,))


@router.get("/api/ad/{code}")
def ad_click(code: str):
    """Tracking link used in the ad. Counts the click for that variant, then opens the store on the product."""
    sku = ""
    try:
        ensure_table()
        rows = db.query("SELECT sku, seller_id FROM ads WHERE id = ?", (code[:16],))
        if rows:
            sku = rows[0]["sku"]
            db.execute("UPDATE ads SET clicks = clicks + 1 WHERE id = ?", (code[:16],))
    except Exception:
        pass   # a broken link must still land on the store
    return RedirectResponse(f"/?ask={sku}&ad={code[:16]}" if sku else "/", status_code=302)
