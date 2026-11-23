"""Long-term memory: facts about a shopper that last across conversations.

Stored in the LangGraph Store (Postgres in production) under ("shoppers", seller_id, user_id).
Saving happens two ways: this deterministic extractor runs on every message (no model call, so it
never forgets), and the model can call remember_preference for anything else.
Recall is code too: the system prompt always includes these facts.
"""
import re

from shopbot.config import CITIES

SIZE = re.compile(
    r"\b(?:size\s*(?:is\s*|hai\s*|:)?\s*(xxs|xs|s|m|l|xl|xxl|small|medium|large|extra large)\b"
    r"|(xxs|xs|s|m|l|xl|xxl|small|medium|large)\s*size\b"
    r"|i (?:wear|am|'m)(?: a)?(?: size)?\s*(xs|s|m|l|xl|xxl|small|medium|large)\b"
    r"|mera size\s*(xs|s|m|l|xl|xxl)\b)",
    re.I)
SHOE = re.compile(r"\b(?:shoe|joota|khussa|foot)\s*size\s*(?:is\s*)?(3[5-9]|4[0-5])\b"
                  r"|\b(3[5-9]|4[0-5])\s*(?:number|size)\s*(?:shoe|joota|khussa)", re.I)
NAME = re.compile(r"\b(?:my name is|mera naam|call me|this is)\s+([A-Za-z][a-z]{1,20})", re.I)
CITY = re.compile(r"\b(?:i live in|i am from|i'm from|im from|based in|main|mai)\s+(\w+)", re.I)
SIZE_WORDS = {"small": "S", "medium": "M", "large": "L", "extra large": "XL"}


def extract(text: str) -> dict:
    facts = {}
    m = SIZE.search(text)
    if m:
        s = next(g for g in m.groups() if g).lower()
        facts["size"] = SIZE_WORDS.get(s, s.upper())
    m = SHOE.search(text)
    if m:
        facts["shoe_size"] = next(g for g in m.groups() if g)
    m = NAME.search(text)
    if m and m.group(1).lower() not in {"a", "the", "not", "looking", "here"}:
        facts["name"] = m.group(1).title()
    m = CITY.search(text)
    if m and m.group(1).lower() in CITIES:
        facts["city"] = m.group(1).title()
    return facts


def recall(store, namespace: tuple) -> str:
    if store is None:
        return "- nothing yet"
    items = store.search(namespace, limit=30)
    lines = [f"- {i.key.split('-')[0].replace('_', ' ')}: {i.value.get('value')}" for i in items]
    return "\n".join(sorted(lines)) or "- nothing yet (new shopper)"
