"""Checking an agent-initiated purchase against its signed mandate (Listing 16.1).

`Mandate` and `check_purchase` are the listing. The module uses the
`cryptography` package when it is installed (see requirements.txt) and
otherwise falls back to the small pure-Python Ed25519 in ed25519_fallback.py,
so the demonstration runs either way with real signatures.

Run:  python mandate.py
  - 10,000 synthetic agent purchases with injected faults, counted by reason
  - the worked example: a $249 purchase against a $150 mandate
"""
from dataclasses import dataclass
from datetime import datetime

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    BACKEND = "cryptography"
except ImportError:  # degrade gracefully: same API, pure Python
    from ed25519_fallback import Ed25519PrivateKey, Ed25519PublicKey, InvalidSignature
    BACKEND = "pure-Python fallback (pip install cryptography for the real library)"


@dataclass(frozen=True)
class Mandate:
    customer_id: str
    agent_id: str
    max_total: float
    categories: frozenset
    confirm_above: float          # the customer must confirm purchases above this
    expires_at: datetime
    payload: bytes                # the exact bytes the customer signed
    signature: bytes


def check_purchase(mandate, cart, customer_key: Ed25519PublicKey):
    """Reasons an agent-initiated purchase falls outside its mandate."""
    try:
        customer_key.verify(mandate.signature, mandate.payload)
    except InvalidSignature:
        return ["the mandate's signature is not the customer's"]
    reasons = []
    if cart.agent_id != mandate.agent_id:
        reasons.append("bought by an agent the customer did not authorize")
    if cart.total > mandate.max_total:
        reasons.append(f"total {cart.total:.2f} over the limit of {mandate.max_total:.2f}")
    if cart.category not in mandate.categories:
        reasons.append(f"category '{cart.category}' not allowed")
    if cart.placed_at > mandate.expires_at:
        reasons.append("placed after the mandate expired")
    if cart.total > mandate.confirm_above and not cart.customer_confirmed:
        reasons.append("no customer confirmation where the mandate required one")
    return reasons


# --------------------------------------------------------------------------
# Synthetic purchases and the worked example
# --------------------------------------------------------------------------
import hashlib  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import timedelta  # noqa: E402

SEED = 16
N_PURCHASES = 10_000
N_CUSTOMERS = 1_000
CATEGORIES = ["electronics", "audio", "groceries", "household", "books", "clothing", "travel", "toys"]
# Injected fault rates (illustrative)
P_OVER_LIMIT = 0.062
P_OVER_LIMIT_CONFIRMED = 0.83      # the customer confirmed, but the limit still binds
P_UNCONFIRMED = 0.021
P_EXPIRED = 0.036
P_WRONG_CATEGORY = 0.034


@dataclass(frozen=True)
class Cart:
    agent_id: str
    total: float
    category: str
    placed_at: datetime
    customer_confirmed: bool


def customer_key(customer_id: str) -> Ed25519PrivateKey:
    """Deterministic demo keys; a real customer's key never leaves their device."""
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(customer_id.encode()).digest())


def sign_mandate(private_key, customer_id, agent_id, max_total, categories, confirm_above, expires_at):
    body = {"customer_id": customer_id, "agent_id": agent_id, "max_total": max_total,
            "categories": sorted(categories), "confirm_above": confirm_above,
            "expires_at": expires_at.isoformat()}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return Mandate(customer_id, agent_id, max_total, frozenset(categories), confirm_above, expires_at,
                   payload, private_key.sign(payload))


def synthetic_purchases(n=N_PURCHASES, customers=N_CUSTOMERS, seed=SEED):
    r = random.Random(seed)
    start = datetime(2026, 9, 1)
    mandates, keys = [], []
    for c in range(customers):
        cid = f"CUST-{c:05d}"
        sk = customer_key(cid)
        max_total = round(r.choice([50, 100, 150, 200, 300, 500]) * 1.0, 2)
        cats = r.sample(CATEGORIES, r.randint(1, 3))
        mandates.append(sign_mandate(sk, cid, f"AGENT-{c % 40:03d}", max_total, cats,
                                     round(max_total * 0.9, 2), start + timedelta(days=r.randint(20, 60))))
        keys.append(sk.public_key())
    out = []
    for i in range(n):
        k = r.randrange(customers)
        m = mandates[k]
        within = r.random() < 0.7
        total = round(m.confirm_above * r.uniform(0.2, 1.0) if within
                      else r.uniform(m.confirm_above + 0.01, m.max_total), 2)
        confirmed = not within
        category = r.choice(sorted(m.categories))
        placed = m.expires_at - timedelta(days=r.uniform(0.5, 15))
        if r.random() < P_OVER_LIMIT:
            total = round(m.max_total * r.uniform(1.05, 1.8), 2)
            confirmed = r.random() < P_OVER_LIMIT_CONFIRMED
        elif r.random() < P_UNCONFIRMED:
            total = round(r.uniform(m.confirm_above + 0.01, m.max_total), 2)
            confirmed = False
        if r.random() < P_EXPIRED:
            placed = m.expires_at + timedelta(days=r.uniform(0.1, 10))
        if r.random() < P_WRONG_CATEGORY:
            category = r.choice([c for c in CATEGORIES if c not in m.categories])
        out.append((m, Cart(m.agent_id, total, category, placed, confirmed), keys[k]))
    return out


def worked_example():
    """The 60,001st claim: an assistant spent $249 against a $150 mandate."""
    sk = customer_key("CUST-WORKED-EXAMPLE")
    mandate = sign_mandate(sk, "CUST-WORKED-EXAMPLE", "AGENT-SHOPPING-ASSISTANT", 150.00,
                           {"headphones", "accessories"}, 135.00, datetime(2026, 12, 31))
    cart = Cart("AGENT-SHOPPING-ASSISTANT", 249.00, "headphones", datetime(2026, 11, 2, 14, 5), False)
    return check_purchase(mandate, cart, sk.public_key())


def main():
    print(f"Ed25519 backend: {BACKEND}")
    purchases = synthetic_purchases()
    counts, outside = Counter(), 0
    for mandate, cart, key in purchases:
        reasons = check_purchase(mandate, cart, key)
        outside += bool(reasons)
        for reason in reasons:
            counts[reason.split(" ")[0] if reason.startswith(("total", "category")) else reason] += 1
    label = {"total": "over the amount allowed", "placed after the mandate expired": "after expiry",
             "category": "outside the allowed categories",
             "no customer confirmation where the mandate required one": "without a required confirmation"}
    print(f"{len(purchases):,} synthetic agent purchases; {outside:,} outside their mandates:")
    for key, name in label.items():
        print(f"  {counts.get(key, 0):5,} {name}")
    # A forged mandate: the payload altered after signing.
    m, cart, key = purchases[0]
    forged = Mandate(m.customer_id, m.agent_id, 10_000.0, m.categories, m.confirm_above, m.expires_at,
                     m.payload.replace(b'"max_total":', b'"max_total":1'), m.signature)
    print("forged mandate ->", check_purchase(forged, cart, key))
    print("\nWorked example ($249 against a $150 mandate, confirmation above $135):")
    for reason in worked_example():
        print("  -", reason)


if __name__ == "__main__":
    main()
