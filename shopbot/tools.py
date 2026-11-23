"""The agent's tools. Every tool reads the shopper and seller from runtime.context (set by the API from the
request body), never from a model argument, so one shopper can never reach another shopper's data.

Prices, stock, totals and discounts are computed here, in code. The model only picks arguments.
"""
import re
from dataclasses import dataclass
from typing import NotRequired
from uuid import uuid4

from langchain.agents import AgentState
from langchain.messages import HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from shopbot import catalog, db
from shopbot.config import (AUTO_DISCOUNT_CAP, DELIVERY, DELIVERY_DEFAULT, FREE_DELIVERY_FROM,
                            ORDER_APPROVAL_LIMIT, SELLERS)


@dataclass
class ShopContext:
    """Who is talking. Comes from the API request, never from the chat."""
    user_id: str
    seller_id: str
    thread_id: str = ""


class ShopState(AgentState):
    """Short-term memory for one conversation: the messages plus the cart."""
    cart: NotRequired[list]            # [{sku, name, size, qty, price}]
    discount: NotRequired[dict]        # {percent, source, status: applied | pending_seller}
    confirm_pending: NotRequired[bool]  # place_order showed a summary and is waiting for "yes"


def memory_ns(ctx: ShopContext) -> tuple:
    """Long-term memory namespace: one per (seller, shopper)."""
    return ("shoppers", ctx.seller_id, ctx.user_id)


def _reply(runtime: ToolRuntime, text: str, **state) -> Command:
    return Command(update={**state, "messages": [ToolMessage(text, tool_call_id=runtime.tool_call_id)]})


# ── catalog ──

@tool
def search_catalog(runtime: ToolRuntime[ShopContext], query: str = "", max_price: int | None = None,
                   size: str | None = None, colour: str | None = None, category: str | None = None) -> str:
    """Search the shop's in-stock products. Use English keywords (wedding, mehndi, eid, casual, winter,
    lawn, men...). size: S/M/L/XL or shoe size like 38. category: suit, kurta, dupatta, shoes or shawl.
    max_price in rupees."""
    items, exact = catalog.search(runtime.context.seller_id, query, max_price, size, colour, category)
    if not items:
        return "No in-stock items match those filters. Suggest relaxing the budget, size or colour."
    head = "" if exact else "No exact match for those words; closest in-stock items within the filters:\n"
    return head + "\n".join(catalog.line(p) for p in items)


@tool
def check_stock(sku: str, runtime: ToolRuntime[ShopContext], size: str | None = None) -> str:
    """Check stock for one product (e.g. SKU-17), optionally in one size. Suggests alternatives if it's out."""
    p = db.product(runtime.context.seller_id, sku)
    if not p:
        return f"{sku} is not in our catalog."
    available = catalog.in_stock_sizes(p)
    size = catalog.norm_size(size)
    text = f"{p['sku']} {p['name']} ({catalog.fmt_price(p['price'])}). "
    if size and p["stock"].get(size, 0) > 0:
        return text + f"Size {size}: {p['stock'][size]} in stock."
    if size:
        text += f"Size {size}: OUT OF STOCK. "
    text += ("In stock: " + ", ".join(f"{k}({v})" for k, v in available.items())) if available else "Fully sold out."
    if (size and p["stock"].get(size, 0) <= 0) or not available:
        alts = catalog.alternatives(runtime.context.seller_id, p, size)
        if alts:
            text += "\nAlternatives" + (f" in {size}" if size else "") + ":\n" + "\n".join(catalog.line(a) for a in alts)
    return text


@tool
def suggest_matching(sku: str, runtime: ToolRuntime[ShopContext]) -> str:
    """Upsell: in-stock items that go with a product the shopper chose (dupatta, khussa, shawl...)."""
    p = db.product(runtime.context.seller_id, sku)
    if not p:
        return f"{sku} is not in our catalog."
    picks = [m for m in (db.product(runtime.context.seller_id, s) for s in p["matches"])
             if m and catalog.in_stock_sizes(m)]
    return "\n".join(catalog.line(m) for m in picks) or "No matching add-ons in stock."


@tool
def delivery_quote(city: str) -> str:
    """Delivery fee and time to a city in Pakistan."""
    fee, days = DELIVERY.get(city.strip().lower(), DELIVERY_DEFAULT)
    return (f"Delivery to {city.title()}: {catalog.fmt_price(fee)}, {days}. "
            f"Free delivery on orders of {catalog.fmt_price(FREE_DELIVERY_FROM)} or more. Cash on delivery available.")


# ── cart (short-term memory, kept in the conversation state) ──

def _cart_text(cart: list, discount: dict | None = None) -> str:
    if not cart:
        return "Cart is empty."
    lines = [f"- {i['qty']} x {i['name']} ({i['sku']}, size {i['size']}) @ {catalog.fmt_price(i['price'])}"
             for i in cart]
    subtotal = sum(i["qty"] * i["price"] for i in cart)
    lines.append(f"Subtotal: {catalog.fmt_price(subtotal)}")
    if discount and discount.get("status") == "applied":
        lines.append(f"Discount: {discount['percent']}% ({discount['source']})")
    elif discount and discount.get("status") == "pending_seller":
        lines.append(f"Discount request: {discount['percent']}% (waiting for the seller's approval)")
    return "\n".join(lines)


@tool
def add_to_cart(sku: str, size: str, runtime: ToolRuntime[ShopContext], qty: int = 1) -> Command:
    """Add a product to the cart. size: S/M/L/XL, a shoe size like 38, or Free for dupattas and shawls."""
    p = db.product(runtime.context.seller_id, sku)
    if not p:
        return _reply(runtime, f"{sku} is not in our catalog.")
    size = catalog.norm_size(size) or ""
    if len(p["stock"]) == 1:                       # one-size items (dupattas, shawls)
        size = next(iter(p["stock"]))
    cart = [dict(i) for i in runtime.state.get("cart", [])]
    have = sum(i["qty"] for i in cart if i["sku"] == p["sku"] and i["size"] == size)
    if p["stock"].get(size, 0) < have + max(qty, 1):
        return _reply(runtime, f"Not enough stock: {p['sku']} size {size} has {p['stock'].get(size, 0)} left. "
                               f"Use check_stock for other sizes or alternatives.")
    for i in cart:
        if i["sku"] == p["sku"] and i["size"] == size:
            i["qty"] += max(qty, 1)
            break
    else:
        cart.append({"sku": p["sku"], "name": p["name"], "size": size, "qty": max(qty, 1), "price": p["price"]})
    return _reply(runtime, "Added.\n" + _cart_text(cart, runtime.state.get("discount")),
                  cart=cart, confirm_pending=False)


@tool
def remove_from_cart(sku: str, runtime: ToolRuntime[ShopContext], size: str | None = None) -> Command:
    """Remove a product (optionally only one size) from the cart."""
    size = catalog.norm_size(size)
    cart = [i for i in runtime.state.get("cart", [])
            if not (i["sku"] == sku.strip().upper() and (size is None or i["size"] == size))]
    return _reply(runtime, "Updated.\n" + _cart_text(cart, runtime.state.get("discount")),
                  cart=cart, confirm_pending=False)


@tool
def view_cart(runtime: ToolRuntime[ShopContext]) -> str:
    """Show the cart with prices and subtotal."""
    return _cart_text(runtime.state.get("cart", []), runtime.state.get("discount"))


@tool
def apply_discount(runtime: ToolRuntime[ShopContext], percent: int = 0, code: str = "") -> Command:
    """Apply a promo code or a requested discount % to the cart. Never decide discounts yourself."""
    seller = SELLERS.get(runtime.context.seller_id, {})
    cart = runtime.state.get("cart", [])
    if code:
        pct = seller.get("promo_codes", {}).get(code.strip().upper())
        if not pct:
            return _reply(runtime, f"Code '{code}' is not valid. No discount applied.")
        discount = {"percent": pct, "source": f"code {code.strip().upper()}", "status": "applied"}
        return _reply(runtime, f"Code applied: {pct}% off.\n" + _cart_text(cart, discount), discount=discount)
    if percent <= 0:
        return _reply(runtime, "Tell me the code or the % the shopper asked for.")
    if not cart:
        return _reply(runtime, f"No discount applied. Discount requests attach to an order, so items must be in "
                               f"the cart first. Above {AUTO_DISCOUNT_CAP}% the seller must approve it.")
    if percent <= AUTO_DISCOUNT_CAP:
        discount = {"percent": percent, "source": "shop offer", "status": "applied"}
        return _reply(runtime, f"{percent}% applied.\n" + _cart_text(cart, discount), discount=discount)
    discount = {"percent": percent, "source": "shopper request", "status": "pending_seller"}
    return _reply(runtime, f"NOT applied. {percent}% is above the {AUTO_DISCOUNT_CAP}% limit, so the request goes "
                           f"to the seller with the order. The order is charged at full price unless the seller "
                           f"approves.\n" + _cart_text(cart, discount), discount=discount)


# ── orders ──

YES = re.compile(r"\b(yes|yeah|yep|yup|confirm|confirmed|ok|okay|sure|haan|han|ji|jee|theek|thik|done|"
                 r"go ahead|place it|kar do|kardo|zaroor|bilkul)\b", re.I)
NO = re.compile(r"\b(no|nope|nahi|nahin|cancel|wait|ruko|mat)\b", re.I)


def _last_human(state) -> str:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return m.text
    return ""


@tool
def place_order(city: str, runtime: ToolRuntime[ShopContext], customer_name: str = "", phone: str = "") -> Command:
    """Place the order for the items in the cart. The first call returns a summary for the shopper to confirm;
    call again only after the shopper says yes."""
    ctx, state = runtime.context, runtime.state
    cart = state.get("cart", [])
    if not cart:
        return _reply(runtime, "Cart is empty. Add items first.")
    discount = state.get("discount") or {}
    subtotal = sum(i["qty"] * i["price"] for i in cart)
    pct = discount.get("percent", 0) if discount.get("status") == "applied" else 0
    after = subtotal - subtotal * pct // 100
    fee = 0 if subtotal >= FREE_DELIVERY_FROM else DELIVERY.get(city.strip().lower(), DELIVERY_DEFAULT)[0]
    total = after + fee
    reasons = []
    if discount.get("status") == "pending_seller":
        reasons.append(f"{discount['percent']}% discount requested")
    if total > ORDER_APPROVAL_LIMIT:
        reasons.append(f"total above {catalog.fmt_price(ORDER_APPROVAL_LIMIT)}")

    said = _last_human(state)
    confirmed = state.get("confirm_pending") and YES.search(said) and not NO.search(said)
    if not confirmed:   # CUSTOM: code, not the model, decides an order needs an explicit "yes"
        summary = (_cart_text(cart, discount) + f"\nDelivery to {city.title()}: {catalog.fmt_price(fee)}"
                   f"\nTotal: {catalog.fmt_price(total)} (cash on delivery)")
        if reasons:
            summary += "\nNeeds the seller's approval after confirming: " + "; ".join(reasons)
        return _reply(runtime, "NOT PLACED YET. Show this summary and ask the shopper to reply 'yes' to confirm:\n"
                      + summary, confirm_pending=True)

    for i in cart:   # re-check stock at the moment of ordering
        p = db.product(ctx.seller_id, i["sku"])
        if not p or p["stock"].get(i["size"], 0) < i["qty"]:
            return _reply(runtime, f"Sorry, {i['name']} size {i['size']} just sold out. Remove it or pick another.",
                          confirm_pending=False)
    for i in cart:
        p = db.product(ctx.seller_id, i["sku"])
        db.set_stock(ctx.seller_id, i["sku"], {**p["stock"], i["size"]: p["stock"][i["size"]] - i["qty"]})

    order_id = "ORD-" + uuid4().hex[:6].upper()
    status = "awaiting_seller" if reasons else "confirmed"
    db.insert_order({
        "id": order_id, "seller_id": ctx.seller_id, "user_id": ctx.user_id, "thread_id": ctx.thread_id,
        "items": cart, "subtotal": subtotal, "discount_percent": discount.get("percent", 0),
        "discount_status": discount.get("status", "none"), "delivery_fee": fee, "total": total,
        "city": city.title(), "customer_name": customer_name, "phone": phone, "status": status,
        "approval_reason": "; ".join(reasons), "created_at": db.now()})
    if runtime.store:   # long-term memory: remember the city for next time
        runtime.store.put(memory_ns(ctx), "city", {"value": city.title()})
    text = f"Order {order_id} placed. Total {catalog.fmt_price(total)}, cash on delivery to {city.title()}."
    text += (f" Status: waiting for the seller's approval ({'; '.join(reasons)})." if reasons
             else " Status: confirmed. The seller will contact the shopper for the address.")
    return _reply(runtime, text, cart=[], discount={}, confirm_pending=False)


@tool
def my_orders(runtime: ToolRuntime[ShopContext]) -> str:
    """This shopper's own recent orders and their status. It can't show anyone else's orders."""
    rows = db.orders_for_user(runtime.context.seller_id, runtime.context.user_id)
    if not rows:
        return "This shopper has no orders yet."
    return "\n".join(f"{o['id']} | {o['created_at'][:10]} | "
                     f"{', '.join(str(i['qty']) + ' x ' + i['name'] for i in o['items'])} | "
                     f"{catalog.fmt_price(o['total'])} | {o['status']}" for o in rows)


# ── long-term memory ──

MEMORY_KINDS = ("name", "size", "shoe_size", "colours", "budget", "style", "city", "other")


@tool
def remember_preference(kind: str, value: str, runtime: ToolRuntime[ShopContext]) -> str:
    """Save a lasting shopper preference for future chats. kind: name, size, shoe_size, colours, budget,
    style, city or other."""
    if not runtime.store:
        return "Memory is not available right now."
    kind = kind.strip().lower() if kind.strip().lower() in MEMORY_KINDS else "other"
    key = kind if kind != "other" else f"other-{uuid4().hex[:6]}"
    runtime.store.put(memory_ns(runtime.context), key, {"value": value.strip()[:200]})
    return f"Remembered {kind}: {value}"


TOOLS = [search_catalog, check_stock, suggest_matching, delivery_quote, add_to_cart, remove_from_cart,
         view_cart, apply_discount, place_order, my_orders, remember_preference]
