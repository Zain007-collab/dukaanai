"""The demo seller's catalog (20 items) and the search logic behind search_catalog.

Search is plain code: keyword + Roman Urdu synonyms + hard filters (price, size, colour, stock).
The model only chooses the arguments; prices and stock always come from here.
"""
import re

from shopbot import db
from shopbot.config import DEFAULT_SELLER

W = ["S", "M", "L", "XL"]   # apparel sizes

# fmt: off
SEED = [
    {"sku": "SKU-01", "name": "Red Lawn 2-Piece Suit", "category": "suit", "colour": "red", "price": 3800,
     "stock": {"S": 3, "M": 4, "L": 2, "XL": 0}, "tags": ["casual", "eid", "summer", "women"], "fabric": "lawn",
     "matches": ["SKU-11", "SKU-16"], "description": "Embroidered neckline, straight trousers. Light for summer."},
    {"sku": "SKU-02", "name": "Maroon Chiffon Wedding Suit", "category": "suit", "colour": "maroon", "price": 4800,
     "stock": {"S": 1, "M": 2, "L": 1, "XL": 1}, "tags": ["wedding", "festive", "party", "women"], "fabric": "chiffon",
     "matches": ["SKU-12", "SKU-16"], "description": "Hand-finished zari work on the front, for shaadi and walima."},
    {"sku": "SKU-03", "name": "Emerald Velvet Festive Suit", "category": "suit", "colour": "green", "price": 7500,
     "stock": {"S": 0, "M": 1, "L": 2, "XL": 1}, "tags": ["wedding", "festive", "winter", "women"], "fabric": "velvet",
     "matches": ["SKU-12", "SKU-20"], "description": "Rich velvet with tilla embroidery, for winter weddings."},
    {"sku": "SKU-04", "name": "Mint Printed Cotton Kurta", "category": "kurta", "colour": "green", "price": 2200,
     "stock": {"S": 5, "M": 5, "L": 3, "XL": 2}, "tags": ["casual", "office", "summer", "women"], "fabric": "cotton",
     "matches": ["SKU-14"], "description": "Everyday printed kurta, breathable cotton."},
    {"sku": "SKU-05", "name": "Black Embroidered Kurti", "category": "kurta", "colour": "black", "price": 2900,
     "stock": {"S": 2, "M": 3, "L": 3, "XL": 1}, "tags": ["office", "party", "women"], "fabric": "cotton silk",
     "matches": ["SKU-13", "SKU-15"], "description": "Short kurti with white thread embroidery."},
    {"sku": "SKU-06", "name": "Pink Organza Party Suit", "category": "suit", "colour": "pink", "price": 5200,
     "stock": {"S": 2, "M": 2, "L": 1, "XL": 0}, "tags": ["party", "wedding", "mehndi", "women"], "fabric": "organza",
     "matches": ["SKU-11", "SKU-16"], "description": "Sheer organza shirt with a silk slip and pearl details."},
    {"sku": "SKU-07", "name": "Yellow Mehndi Suit", "category": "suit", "colour": "yellow", "price": 4500,
     "stock": {"S": 1, "M": 3, "L": 2, "XL": 1}, "tags": ["mehndi", "wedding", "festive", "women"], "fabric": "jacquard",
     "matches": ["SKU-11", "SKU-16"], "description": "Bright jacquard with gota lace, made for mehndi night."},
    {"sku": "SKU-08", "name": "Navy Khaddar Suit", "category": "suit", "colour": "blue", "price": 3500,
     "stock": {"S": 2, "M": 3, "L": 4, "XL": 2}, "tags": ["winter", "casual", "women"], "fabric": "khaddar",
     "matches": ["SKU-20", "SKU-14"], "description": "Warm khaddar for winter, block-printed border."},
    {"sku": "SKU-09", "name": "Ivory Chikankari Kurta", "category": "kurta", "colour": "white", "price": 3200,
     "stock": {"S": 3, "M": 2, "L": 2, "XL": 1}, "tags": ["eid", "casual", "summer", "women"], "fabric": "cotton",
     "matches": ["SKU-13", "SKU-16"], "description": "Classic chikankari hand embroidery."},
    {"sku": "SKU-10", "name": "Peach Lawn 2-Piece Suit", "category": "suit", "colour": "peach", "price": 2700,
     "stock": {"S": 4, "M": 0, "L": 3, "XL": 2}, "tags": ["casual", "summer", "women"], "fabric": "lawn",
     "matches": ["SKU-14"], "description": "Soft pastel lawn, printed shirt with plain trousers."},
    {"sku": "SKU-11", "name": "Gold Tissue Dupatta", "category": "dupatta", "colour": "gold", "price": 1500,
     "stock": {"Free": 6}, "tags": ["wedding", "festive", "mehndi", "women"], "fabric": "tissue",
     "matches": ["SKU-06", "SKU-07"], "description": "Shimmering tissue dupatta that lifts any plain suit."},
    {"sku": "SKU-12", "name": "Maroon Banarsi Dupatta", "category": "dupatta", "colour": "maroon", "price": 2400,
     "stock": {"Free": 3}, "tags": ["wedding", "festive", "women"], "fabric": "banarsi",
     "matches": ["SKU-02", "SKU-03"], "description": "Woven banarsi dupatta with a heavy border."},
    {"sku": "SKU-13", "name": "Black Chiffon Dupatta", "category": "dupatta", "colour": "black", "price": 1100,
     "stock": {"Free": 8}, "tags": ["casual", "party", "women"], "fabric": "chiffon",
     "matches": ["SKU-05", "SKU-09"], "description": "Plain chiffon dupatta with a thin lace edge."},
    {"sku": "SKU-14", "name": "Printed Lawn Dupatta", "category": "dupatta", "colour": "multi", "price": 900,
     "stock": {"Free": 10}, "tags": ["casual", "summer", "women"], "fabric": "lawn",
     "matches": ["SKU-04", "SKU-10"], "description": "Light printed lawn dupatta for everyday wear."},
    {"sku": "SKU-15", "name": "Black Kolhapuri Chappal", "category": "shoes", "colour": "black", "price": 1800,
     "stock": {"36": 2, "37": 3, "38": 3, "39": 1, "40": 0}, "tags": ["casual", "women"], "fabric": "leather",
     "matches": ["SKU-05"], "description": "Handmade leather kolhapuri, cushioned sole."},
    {"sku": "SKU-16", "name": "Golden Embroidered Khussa", "category": "shoes", "colour": "gold", "price": 2200,
     "stock": {"36": 1, "37": 2, "38": 2, "39": 2, "40": 1}, "tags": ["wedding", "eid", "festive", "women"],
     "fabric": "leather", "matches": ["SKU-02", "SKU-07"], "description": "Traditional khussa with gold tilla."},
    {"sku": "SKU-17", "name": "Ruby Red Bridal Shirt & Sharara", "category": "suit", "colour": "red", "price": 9500,
     "stock": {"S": 1, "M": 1, "L": 1, "XL": 0}, "tags": ["wedding", "bridal", "festive", "women"], "fabric": "raw silk",
     "matches": ["SKU-12", "SKU-16"], "description": "Raw silk shirt with a flared sharara, heavy dabka work."},
    {"sku": "SKU-18", "name": "Men's White Kurta Shalwar", "category": "kurta", "colour": "white", "price": 3400,
     "stock": {"S": 2, "M": 4, "L": 4, "XL": 3}, "tags": ["eid", "casual", "men"], "fabric": "wash and wear",
     "matches": ["SKU-19"], "description": "Crisp wash-and-wear kurta shalwar for Eid and Friday prayers."},
    {"sku": "SKU-19", "name": "Men's Brown Peshawari Chappal", "category": "shoes", "colour": "brown", "price": 2600,
     "stock": {"40": 2, "41": 3, "42": 3, "43": 2, "44": 1}, "tags": ["eid", "casual", "men"], "fabric": "leather",
     "matches": ["SKU-18"], "description": "Hand-stitched peshawari chappal."},
    {"sku": "SKU-20", "name": "Kashmiri Embroidered Shawl", "category": "shawl", "colour": "beige", "price": 4200,
     "stock": {"Free": 4}, "tags": ["winter", "wedding", "women"], "fabric": "pashmina blend",
     "matches": ["SKU-08", "SKU-03"], "description": "Soft shawl with Kashmiri aari embroidery."},
]
# fmt: on

# Roman Urdu / Urdu-English words shoppers use, mapped to catalog words
SYNONYMS = {
    "shaadi": "wedding", "shadi": "wedding", "shaadi's": "wedding", "barat": "wedding", "baraat": "wedding",
    "walima": "wedding", "nikah": "wedding", "dulhan": "bridal", "bride": "bridal", "mehendi": "mehndi",
    "mayun": "mehndi", "laal": "red", "lal": "red", "surkh": "red", "kala": "black", "kaala": "black",
    "safed": "white", "safaid": "white", "sufaid": "white", "neela": "blue", "nila": "blue", "hara": "green",
    "peela": "yellow", "pila": "yellow", "gulabi": "pink", "sunehra": "gold", "golden": "gold",
    "joota": "shoes", "jootay": "shoes", "juta": "shoes", "jooti": "shoes", "khussa": "shoes", "chappal": "shoes",
    "sandal": "shoes", "sandals": "shoes", "shoe": "shoes", "footwear": "shoes",
    "jora": "suit", "joda": "suit", "suits": "suit", "dress": "suit", "dresses": "suit", "outfit": "suit",
    "kurti": "kurta", "kurtas": "kurta", "kameez": "kurta", "qameez": "kurta", "shirt": "kurta",
    "chunri": "dupatta", "chunni": "dupatta", "dupattas": "dupatta", "scarf": "dupatta",
    "chadar": "shawl", "chaadar": "shawl", "shawls": "shawl",
    "gents": "men", "mens": "men", "man": "men", "male": "men", "mard": "men",
    "ladies": "women", "womens": "women", "woman": "women", "female": "women", "girls": "women",
    "garmi": "summer", "sardi": "winter", "sardiyon": "winter", "daftar": "office", "work": "office",
    "eidi": "eid", "rozana": "casual", "everyday": "casual", "daily": "casual",
}
COLOUR_FAMILY = {"maroon": "red", "peach": "orange", "gold": "yellow", "beige": "white", "ivory": "white",
                 "mint": "green", "navy": "blue"}
SIZE_WORDS = {"small": "S", "medium": "M", "large": "L", "extra large": "XL", "xlarge": "XL", "x-large": "XL"}
STOPWORDS = {"a", "an", "the", "for", "with", "and", "or", "in", "of", "to", "me", "my", "some", "any", "under",
             "below", "size", "show", "want", "need", "looking", "something", "ke", "liye", "kuch", "chahiye",
             "tak", "hai", "koi", "mujhe", "please", "item", "items", "do", "you", "have"}


def seed_products() -> None:
    if not db.query("SELECT sku FROM products WHERE seller_id = ? LIMIT 1", (DEFAULT_SELLER,)):
        for p in SEED:
            db.upsert_product(DEFAULT_SELLER, p)


def norm_size(size: str | None) -> str | None:
    if not size:
        return None
    s = SIZE_WORDS.get(size.strip().lower(), size.strip().lower())
    return "Free" if s in ("free", "free size", "one size") else s.upper()


def in_stock_sizes(p: dict) -> dict:
    return {k: v for k, v in p["stock"].items() if v > 0}


def fmt_price(n: int) -> str:
    return f"Rs {n:,}"


def line(p: dict) -> str:
    sizes = ", ".join(f"{k}({v})" for k, v in in_stock_sizes(p).items()) or "SOLD OUT"
    return (f"{p['sku']} | {p['name']} | {fmt_price(p['price'])} | in stock: {sizes} | "
            f"{p['fabric']}, {', '.join(p['tags'])}")


def _words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        w = SYNONYMS.get(w, w)
        if w not in STOPWORDS and not w.isdigit():
            out.append(w)
    return out


def _haystack(p: dict) -> set[str]:
    words = set(_words(f"{p['name']} {p['category']} {p['colour']} {p['fabric']} {' '.join(p['tags'])}"))
    words.add(COLOUR_FAMILY.get(p["colour"], p["colour"]))
    return words


def search(seller_id: str, query: str = "", max_price: int | None = None, size: str | None = None,
           colour: str | None = None, category: str | None = None, limit: int = 5) -> tuple[list[dict], bool]:
    """Return (items, exact). exact=False means no keyword matched and we fell back to the filters alone."""
    size = norm_size(size)
    colour = SYNONYMS.get(colour.lower(), colour.lower()) if colour else None
    category = SYNONYMS.get(category.lower(), category.lower()) if category else None

    def passes(p):
        if max_price and p["price"] > max_price:
            return False
        if size and p["stock"].get(size, 0) <= 0 and not (p["category"] in ("dupatta", "shawl")):
            return False
        if not in_stock_sizes(p):
            return False
        if colour and colour not in (p["colour"], COLOUR_FAMILY.get(p["colour"])):
            return False
        if category and category != p["category"]:
            return False
        return True

    pool = [p for p in db.products(seller_id) if passes(p)]
    words = _words(query or "")
    if not words:
        return sorted(pool, key=lambda p: p["price"])[:limit], True
    scored = [(sum(w in _haystack(p) for w in words), p) for p in pool]
    best = max((s for s, _ in scored), default=0)
    if best > 0:
        # only the best matches; with a size given, clothes in that size come before one-size accessories
        hits = [p for s, p in scored if s == best]
        hits.sort(key=lambda p: (bool(size) and size not in p["stock"], p["price"]))
        return hits[:limit], True
    return sorted(pool, key=lambda p: p["price"])[:limit], False


def alternatives(seller_id: str, p: dict, size: str | None, limit: int = 2) -> list[dict]:
    """Similar in-stock items (same category, shared tags), in the requested size if given."""
    size = norm_size(size)
    out = []
    for q in db.products(seller_id):
        if q["sku"] == p["sku"] or q["category"] != p["category"]:
            continue
        if size and q["stock"].get(size, 0) <= 0:
            continue
        if not in_stock_sizes(q):
            continue
        out.append((len(set(q["tags"]) & set(p["tags"])), abs(q["price"] - p["price"]), q))
    return [q for _, _, q in sorted(out, key=lambda t: (-t[0], t[1]))][:limit]
