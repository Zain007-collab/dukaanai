"""Settings and seller policy. Secrets come from the environment (.env locally, Vercel env vars in prod)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "claude-haiku-5-5"   # the graded model; always used in production
# Local testing only: LLM_PROVIDER=gemini runs the same agent on Gemini to save the Claude budget
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude").strip().lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "dukaan-admin").strip()

# Haiku 5.5 list price per million tokens (prompts up to 100K), for the cost panel on the dashboard
PRICE_IN_PER_M = 0.10
PRICE_OUT_PER_M = 0.50

DEFAULT_SELLER = "dukaan-demo"

# CUSTOM: seller policy. In a multi-seller deployment this row lives in a sellers table.
SELLERS = {
    "dukaan-demo": {
        "name": "Noor Boutique",
        "city": "Islamabad",
        "promo_codes": {"EID10": 10, "WELCOME5": 5},
    },
}

AUTO_DISCOUNT_CAP = 10          # % a shopper can get without the seller (plan: approval above 10%)
ORDER_APPROVAL_LIMIT = 15000    # Rs: orders above this wait for the seller's approval
FREE_DELIVERY_FROM = 10000      # Rs: subtotal at which delivery is free

DELIVERY = {                    # city -> (fee in Rs, days)
    "islamabad": (200, "1-2 days"),
    "rawalpindi": (200, "1-2 days"),
    "lahore": (300, "2-3 days"),
    "peshawar": (300, "2-3 days"),
    "faisalabad": (300, "2-3 days"),
    "multan": (350, "3-4 days"),
    "karachi": (350, "3-5 days"),
}
DELIVERY_DEFAULT = (400, "4-6 days")

CITIES = sorted(DELIVERY) + ["quetta", "sialkot", "hyderabad", "gujranwala", "abbottabad", "murree"]
