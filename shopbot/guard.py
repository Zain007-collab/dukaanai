"""Guard node: refuses prompt injection and clearly off-topic requests in code, before any model call.

A prompt is a request; this is enforcement. Subtler off-topic requests are still caught by the
system prompt, but these never reach the model at all (zero tokens).
"""
import re

INJECTION = re.compile(
    r"ignore (all |any |the |your |previous |prior |above )*(rules|instructions|prompts?|guidelines)"
    r"|disregard (all |the |your |previous )*(rules|instructions)"
    r"|forget (all |your |the |previous )*(rules|instructions)"
    r"|(system|developer|hidden) prompt|your (instructions|prompt|rules) (are|say)"
    r"|reveal (your|the) (prompt|instructions|rules)"
    r"|you are now|act as (an? )?(admin|developer|seller|owner|dan|system)|pretend (to be|you are)"
    r"|developer mode|admin mode|god mode|jailbreak|(?-i:\bDAN\b)|sudo "
    # other people's data. ("show all my orders" is fine: tools only ever return the caller's own.)
    r"|(other|another|all|every|everyone'?s?)\s+(users?|customers?|shoppers?|buyers?|people)('s|s')?\s+"
    r"(orders?|data|details|info|address\w*|phones?|numbers?|history|memor\w*|names?)"
    r"|(orders?|data|details|history|address\w*|info) (of|for|from) (all |other |another |every )?"
    r"(users?|customers?|shoppers?|buyers?|someone)|someone else'?s"
    r"|user_id|thread_id|seller_id|select \* from|drop table|<script",
    re.I)

OFF_TOPIC = re.compile(
    r"\b(homework|assignment|essay|thesis|python|javascript|java|c\+\+|sql query|leetcode|algorithm"
    r"|write (me )?(a |an |my )?(code|program|script|function|poem|story|song|essay|letter|cv|resume)"
    r"|solve (this|the|my)|equation|integral|derivative|calculus|physics|chemistry"
    r"|capital of|prime minister|president|election|politic\w*|imran khan|cricket score"
    r"|weather (today|forecast|in \w+)|what'?s the weather|(latest|today'?s|breaking) news"
    r"|recipe|bitcoin|crypto|stock market|forex|lottery|horoscope|diagnos\w*|medicine|prescription|lawyer|legal advice"
    r"|translate (this|the following))\b",
    re.I)

# A few common Roman Urdu words, to answer in the shopper's language
ROMAN_URDU = re.compile(r"\b(hai|hain|kya|kia|mujhe|mujhay|chahiye|chahye|aap|ap|mera|meri|nahi|karo|kar|"
                        r"bhai|yaar|batao|dikhao|kitne|kitna|ka|ki|ke|wala|wali)\b", re.I)

REFUSE_INJECTION = {
    "en": "Sorry, I can't do that. I can only help you shop here, and I can only ever show your own orders. "
          "Would you like to see our new arrivals or check your order?",
    "ur": "Maaf kijiye, yeh main nahi kar sakta. Main sirf shopping mein madad karta hoon aur sirf aap ke apne "
          "orders dikha sakta hoon. Kya aap new arrivals dekhna chahenge ya apna order check karna hai?",
}
REFUSE_OFF_TOPIC = {
    "en": "I'm the shop assistant here, so I can only help with our clothes, orders and delivery. "
          "Are you shopping for something special, like Eid, a wedding or everyday wear?",
    "ur": "Main is dukaan ka assistant hoon, is liye sirf kapron, orders aur delivery mein madad kar sakta hoon. "
          "Kisi khaas mauqe ke liye kuch chahiye? Eid, shaadi ya rozana ke liye?",
}
TOO_LONG = {"en": "That message is too long for me. Please send a shorter question about our products.",
            "ur": "Yeh message bohat lamba hai. Barah-e-karam products ke baare mein chhota sawal bhejein."}
MAX_CHARS = 1500


def check(text: str) -> tuple[str, str] | None:
    """Return (kind, reply) if the message must be refused, else None."""
    lang = "ur" if len(ROMAN_URDU.findall(text)) >= 2 else "en"
    if len(text) > MAX_CHARS:
        return "too_long", TOO_LONG[lang]
    if INJECTION.search(text):
        return "injection", REFUSE_INJECTION[lang]
    if OFF_TOPIC.search(text):
        return "off_topic", REFUSE_OFF_TOPIC[lang]
    return None
