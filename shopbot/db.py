"""A tiny data layer: Neon Postgres in production, SQLite for local dev. The same SQL runs on both.

Every query that touches shopper data is filtered by seller_id AND user_id, both taken from the
request context (never from the model).
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from shopbot.config import DATABASE_URL, ROOT

IS_PG = DATABASE_URL.startswith("postgres")
_pool = None
_sqlite = None
_lock = threading.Lock()


def pool():
    """The shared Postgres pool (also used by the LangGraph checkpointer and store)."""
    global _pool
    if _pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(
            DATABASE_URL, min_size=1, max_size=5, open=True,
            check=ConnectionPool.check_connection,   # Neon closes idle connections: re-check before use
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
    return _pool


def _sqlite_conn():
    global _sqlite
    if _sqlite is None:
        _sqlite = sqlite3.connect(os.getenv("LOCAL_DB", str(ROOT / "local.db")), check_same_thread=False)
        _sqlite.row_factory = sqlite3.Row
    return _sqlite


def query(sql: str, params=()) -> list[dict]:
    if IS_PG:
        with pool().connection() as conn:
            cur = conn.execute(sql.replace("?", "%s"), params)
            return list(cur.fetchall()) if cur.description else []
    with _lock:
        conn = _sqlite_conn()
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        conn.commit()
        return rows


def execute(sql: str, params=()) -> None:
    query(sql, params)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS products (
        seller_id TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
        colour TEXT NOT NULL, price INTEGER NOT NULL, stock TEXT NOT NULL, tags TEXT NOT NULL,
        fabric TEXT NOT NULL, matches TEXT NOT NULL, description TEXT NOT NULL,
        PRIMARY KEY (seller_id, sku))""",
    """CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY, seller_id TEXT NOT NULL, user_id TEXT NOT NULL, thread_id TEXT NOT NULL,
        items TEXT NOT NULL, subtotal INTEGER NOT NULL, discount_percent INTEGER NOT NULL,
        discount_status TEXT NOT NULL, delivery_fee INTEGER NOT NULL, total INTEGER NOT NULL,
        city TEXT NOT NULL, customer_name TEXT NOT NULL, phone TEXT NOT NULL, status TEXT NOT NULL,
        approval_reason TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS flags (
        id TEXT PRIMARY KEY, seller_id TEXT NOT NULL, user_id TEXT NOT NULL, kind TEXT NOT NULL,
        message TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS usage_log (
        id TEXT PRIMARY KEY, seller_id TEXT NOT NULL, user_id TEXT NOT NULL, tokens_in INTEGER NOT NULL,
        tokens_out INTEGER NOT NULL, tool_calls INTEGER NOT NULL, latency_ms INTEGER NOT NULL,
        blocked INTEGER NOT NULL, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS orders_owner ON orders (seller_id, user_id)",
]

_ready = False


def init_db() -> None:
    """Create tables and seed the demo catalog once per process. Safe to call on every cold start."""
    global _ready
    if _ready:
        return
    from shopbot.catalog import seed_products
    for stmt in SCHEMA:
        execute(stmt)
    seed_products()
    _ready = True


# ── products ──

def _product(row: dict) -> dict:
    row = dict(row)
    row["stock"] = json.loads(row["stock"])
    row["tags"] = json.loads(row["tags"])
    row["matches"] = json.loads(row["matches"])
    return row


def products(seller_id: str) -> list[dict]:
    return [_product(r) for r in query("SELECT * FROM products WHERE seller_id = ? ORDER BY sku", (seller_id,))]


def product(seller_id: str, sku: str) -> dict | None:
    rows = query("SELECT * FROM products WHERE seller_id = ? AND sku = ?", (seller_id, sku.strip().upper()))
    return _product(rows[0]) if rows else None


def upsert_product(seller_id: str, p: dict) -> None:
    execute("DELETE FROM products WHERE seller_id = ? AND sku = ?", (seller_id, p["sku"]))
    execute(
        "INSERT INTO products (seller_id, sku, name, category, colour, price, stock, tags, fabric, matches, description)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (seller_id, p["sku"], p["name"], p["category"], p["colour"], int(p["price"]), json.dumps(p["stock"]),
         json.dumps(p.get("tags", [])), p.get("fabric", ""), json.dumps(p.get("matches", [])),
         p.get("description", "")))


def set_stock(seller_id: str, sku: str, stock: dict) -> None:
    execute("UPDATE products SET stock = ? WHERE seller_id = ? AND sku = ?", (json.dumps(stock), seller_id, sku))


# ── orders ──

def _order(row: dict) -> dict:
    row = dict(row)
    row["items"] = json.loads(row["items"])
    return row


def insert_order(o: dict) -> None:
    execute(
        "INSERT INTO orders (id, seller_id, user_id, thread_id, items, subtotal, discount_percent, discount_status,"
        " delivery_fee, total, city, customer_name, phone, status, approval_reason, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (o["id"], o["seller_id"], o["user_id"], o["thread_id"], json.dumps(o["items"]), o["subtotal"],
         o["discount_percent"], o["discount_status"], o["delivery_fee"], o["total"], o["city"],
         o["customer_name"], o["phone"], o["status"], o["approval_reason"], o["created_at"]))


def orders_for_user(seller_id: str, user_id: str, limit: int = 5) -> list[dict]:
    rows = query("SELECT * FROM orders WHERE seller_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
                 (seller_id, user_id, limit))
    return [_order(r) for r in rows]


def orders_for_seller(seller_id: str, status: str | None = None) -> list[dict]:
    if status:
        rows = query("SELECT * FROM orders WHERE seller_id = ? AND status = ? ORDER BY created_at DESC",
                     (seller_id, status))
    else:
        rows = query("SELECT * FROM orders WHERE seller_id = ? ORDER BY created_at DESC", (seller_id,))
    return [_order(r) for r in rows]


def order(seller_id: str, order_id: str) -> dict | None:
    rows = query("SELECT * FROM orders WHERE seller_id = ? AND id = ?", (seller_id, order_id))
    return _order(rows[0]) if rows else None


def update_order(seller_id: str, order_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    execute(f"UPDATE orders SET {cols} WHERE seller_id = ? AND id = ?", (*fields.values(), seller_id, order_id))


# ── flags and usage (for the dashboard) ──

def add_flag(seller_id: str, user_id: str, kind: str, message: str, flag_id: str) -> None:
    execute("INSERT INTO flags (id, seller_id, user_id, kind, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (flag_id, seller_id, user_id, kind, message[:500], now()))


def flags(seller_id: str, limit: int = 50) -> list[dict]:
    return query("SELECT * FROM flags WHERE seller_id = ? ORDER BY created_at DESC LIMIT ?", (seller_id, limit))


def log_usage(row: dict) -> None:
    execute("INSERT INTO usage_log (id, seller_id, user_id, tokens_in, tokens_out, tool_calls, latency_ms, blocked,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], row["seller_id"], row["user_id"], row["tokens_in"], row["tokens_out"], row["tool_calls"],
             row["latency_ms"], row["blocked"], now()))


def usage_totals(seller_id: str) -> dict:
    rows = query("SELECT COUNT(*) AS chats, COALESCE(SUM(tokens_in), 0) AS tokens_in,"
                 " COALESCE(SUM(tokens_out), 0) AS tokens_out, COALESCE(AVG(latency_ms), 0) AS avg_latency_ms"
                 " FROM usage_log WHERE seller_id = ?", (seller_id,))
    return {k: (int(v) if v is not None else 0) for k, v in rows[0].items()}
