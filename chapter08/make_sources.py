"""Generate the four synthetic source feeds of Chapter 8 and a truth file.

Outputs (all in this folder):
  authorization.csv   3,000 authorizations from the issuer's processor
  clearing.csv        3,000 clearing records from the network (9% lack an auth code)
  merchant_order.csv  3,000 merchant orders (about 30% lack an auth code)
  crm_claim.csv       435 claims as the customer reported them
  truth_links.csv     the true clearing, authorization and order behind each claim
                      (rows with a claim_id), and the true authorization and order
                      behind every clearing record (rows without one)

The generator is seeded and deterministic. The feeds are built so that the
situations described in the chapter all occur with the frequencies the
chapter reports: clean name matches, amount-only matches, monthly
subscriptions that make the claim ambiguous, claims that cannot be linked,
duplicate claims, clearing records missing their authorization code, orders
missing it, and six clearing records dated before their own authorization.
Each claim is constructed for a scenario and then checked with the linking
rules of linking.py, so the scenario mix is exact while the records
themselves are random. All data are synthetic.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from linking import link_claim, match, similar

warnings.filterwarnings("ignore", category=DeprecationWarning)   # numpy 2 / pandas timedelta notice
HERE = Path(__file__).resolve().parent
SEED = 8
rng = np.random.default_rng(SEED)

N_TXN = 3000
N_CARDS = 1000
N_SERIES = 70                     # monthly subscriptions, six charges each
N_STORE_TXN = 150                 # card-present purchases: no merchant order
N_CLEARING_NO_CODE = 270          # 9.0% of clearing records
N_CLR_MISSING_ONLINE = 225       # of which at merchants that ship goods
N_ORDER_CODED = 2091              # 69.7% of merchant orders
N_ORDER_CODED_CLR_MISSING = 198   # coded orders whose clearing record has no code
N_TIME_VIOLATIONS = 6
WORKED_IDX = 2838                 # A02839 / O02839
YEAR_START = pd.Timestamp("2025-01-01")
WORKED_CLAIM_AT = pd.Timestamp("2025-03-20 11:31")

MERCHANTS = [
    # (name, kind) -- kind: online (ships goods), subscription (monthly box), store (card present)
    ("Granite Toys", "online"), ("Harbor Books", "online"), ("Cobalt Electronics", "online"),
    ("Juniper Home", "online"), ("Saffron Kitchen", "online"), ("Northwind Outdoor", "online"),
    ("Pebble Pets", "online"), ("Velvet Fashion", "online"), ("Atlas Sports", "online"),
    ("Meadow Garden", "online"), ("Orbit Gadgets", "online"), ("Quill Stationery", "online"),
    ("Riverstone Shoes", "online"), ("Summit Gear", "online"), ("Tidewater Audio", "online"),
    ("Umber Furniture", "online"), ("Willow Beauty", "online"), ("Zephyr Cycles", "online"),
    ("Beacon Lighting", "online"), ("Crescent Jewelry", "online"), ("Driftwood Art", "online"),
    ("Ember Coffee", "online"), ("Falcon Optics", "online"), ("Glacier Water", "online"),
    ("Hollow Vinyl", "online"), ("Ivory Linen", "online"), ("Kestrel Games", "online"),
    ("Lantern Crafts", "online"),
    ("Bloom Box", "subscription"), ("Fresh Crate", "subscription"), ("Pixel Club", "subscription"),
    ("Sprout Meals", "subscription"), ("Vista Magazines", "subscription"), ("Nimbus Wine", "subscription"),
    ("Corner Grocer", "store"), ("Main Street Fuel", "store"), ("Elm Pharmacy", "store"),
    ("Station Diner", "store"), ("Oak Hardware", "store"), ("Plaza Cinema", "store"),
]
GENERIC_NAMES = ["online store", "internet purchase", "web shop", "unknown merchant",
                 "a shop", "the website", "online order", "some company", "a seller",
                 "retailer", "app purchase", "not sure"]
CHANNELS = ["app", "web", "phone", "branch"]
CHANNEL_P = [0.45, 0.25, 0.25, 0.05]


def descriptor(name):
    return name.upper().replace(" ", "") + "*" + f"{rng.integers(1000, 10000)}"


def ts(day_offset, hour=None, minute=None):
    hour = int(rng.integers(7, 23)) if hour is None else hour
    minute = int(rng.integers(0, 60)) if minute is None else minute
    return YEAR_START + pd.Timedelta(days=int(day_offset)) + pd.Timedelta(hours=hour, minutes=minute)


def money(x):
    return float(np.round(x, 2))


# ---------------------------------------------------------------- merchants, cards
merchants = pd.DataFrame(MERCHANTS, columns=["merchant_name", "kind"])
merchants["merchant_id"] = [f"M{i:03d}" for i in range(1, len(merchants) + 1)]
merchants["descriptor"] = [descriptor(n) for n in merchants.merchant_name]
merchants.loc[merchants.merchant_name == "Granite Toys", "descriptor"] = "GRANITETOYS*5274"
mrec = merchants.set_index("merchant_id")
cards = [f"tok_{x:08x}" for x in rng.choice(16**8, size=N_CARDS + 50, replace=False)]
spare_cards = cards[N_CARDS:]          # cards that never appear in the feeds
cards = cards[:N_CARDS]
by_kind = {k: merchants[merchants.kind == k].merchant_id.tolist() for k in merchants.kind.unique()}

# ---------------------------------------------------------------- transactions
txns = []
for _ in range(N_SERIES):
    card, mid = rng.choice(cards), rng.choice(by_kind["subscription"])
    amount, day = money(rng.uniform(8, 60)), int(rng.integers(0, 28))
    hour, minute = int(rng.integers(0, 6)), int(rng.integers(0, 60))
    for month in range(6):
        when = (YEAR_START + pd.DateOffset(months=month) + pd.Timedelta(days=day)
                + pd.Timedelta(hours=hour, minutes=minute))
        txns.append(dict(card_token=card, merchant_id=mid, amount=amount, authorized_at=when))
n_oneoff = N_TXN - len(txns)
online = by_kind["online"]
weights = rng.dirichlet(np.full(len(online), 12.0))      # merchant popularity
for i in range(n_oneoff):
    store = i < N_STORE_TXN
    mid = rng.choice(by_kind["store"]) if store else rng.choice(online, p=weights)
    amount = money(np.exp(rng.normal(4.2, 0.8)))
    txns.append(dict(card_token=rng.choice(cards), merchant_id=mid, amount=max(amount, 3.0),
                     authorized_at=ts(rng.integers(0, 181))))
order = rng.permutation(len(txns))
txn = pd.DataFrame([txns[i] for i in order]).reset_index(drop=True)

# the worked example: A02839 at Granite Toys, $127.11, 1 March 08:39
granite = merchants.loc[merchants.merchant_name == "Granite Toys", "merchant_id"].item()
worked_card = spare_cards.pop()
txn.loc[WORKED_IDX, ["card_token", "merchant_id", "amount", "authorized_at"]] = [
    worked_card, granite, 127.11, pd.Timestamp("2025-03-01 08:39")]
txn["kind"] = txn.merchant_id.map(mrec.kind)
txn["auth_id"] = [f"A{i:05d}" for i in range(1, N_TXN + 1)]
codes = set()
while len(codes) < N_TXN + 1:
    codes.add(f"{rng.integers(0, 16**6):06X}")
codes.discard("5006F2")
txn["auth_code"] = sorted(codes, key=lambda c: rng.random())[:N_TXN]
txn.loc[WORKED_IDX, "auth_code"] = "5006F2"

# clearing: final amount and settlement one to three days after authorization
txn["cleared_at"] = txn.authorized_at + pd.to_timedelta(rng.uniform(1.0, 3.0, N_TXN), unit="D")
txn["cleared_at"] = txn.cleared_at.dt.floor("min")
txn.loc[WORKED_IDX, "cleared_at"] = pd.Timestamp("2025-03-03 02:14")
txn["cleared_amount"] = txn.amount
adjust = rng.random(N_TXN) < 0.03
adjust[WORKED_IDX] = False
txn.loc[adjust, "cleared_amount"] = (txn.amount[adjust] * (1 + rng.uniform(-0.008, 0.008, adjust.sum()))).round(2)
txn["arn"] = ["".join(map(str, rng.integers(0, 10, 23))) for _ in range(N_TXN)]
txn.loc[WORKED_IDX, "arn"] = "74837265063200498117365"

# which clearing records lose their auth code, which orders keep theirs
idx = np.arange(N_TXN)
has_order = (txn.kind != "store").to_numpy()
pick = rng.permutation(np.setdiff1d(idx, [WORKED_IDX]))
online_idx = [i for i in pick if has_order[i]]
store_idx = [i for i in pick if not has_order[i]]
clr_missing = set(online_idx[:N_CLR_MISSING_ONLINE]) | set(store_idx[:N_CLEARING_NO_CODE - N_CLR_MISSING_ONLINE])
clr_coded_online = online_idx[N_CLR_MISSING_ONLINE:]
order_coded = set(online_idx[:N_ORDER_CODED_CLR_MISSING])               # clearing missing
order_coded |= set(clr_coded_online[:N_ORDER_CODED - N_ORDER_CODED_CLR_MISSING])
assert WORKED_IDX not in order_coded and WORKED_IDX not in clr_missing
txn["clr_has_code"] = ~txn.index.isin(clr_missing)
txn["order_has_code"] = txn.index.isin(order_coded)

# six clearing records dated before their own authorization (a clock error)
violators = rng.choice([i for i in pick if i not in clr_missing], N_TIME_VIOLATIONS, replace=False)
txn.loc[violators, "cleared_at"] = (txn.authorized_at[violators]
                                    - pd.to_timedelta(rng.uniform(1, 9, N_TIME_VIOLATIONS), unit="h")).dt.floor("min")

# merchant orders for every online and subscription purchase
orders = txn[has_order].copy()
orders["order_id"] = "O" + orders.auth_id.str[1:]
orders["ordered_at"] = orders.authorized_at - pd.to_timedelta(rng.integers(1, 20, len(orders)), unit="min")
orders["shipped_at"] = (orders.authorized_at + pd.to_timedelta(rng.uniform(1, 4, len(orders)), unit="D")).dt.floor("h")
orders["delivered_at"] = (orders.shipped_at + pd.to_timedelta(rng.uniform(2, 7, len(orders)), unit="D")).dt.floor("h")
lost = rng.random(len(orders)) < 0.04
orders.loc[lost, "delivered_at"] = pd.NaT
orders.loc[orders.auth_id == "A02839", ["shipped_at", "delivered_at"]] = [
    pd.Timestamp("2025-03-05 14:00"), pd.Timestamp("2025-03-11 10:00")]
orders["delivery_status"] = np.where(orders.delivered_at.isna(), "in_transit", "delivered")
orders["auth_code"] = orders.auth_code.where(orders.order_has_code)
orders["order_total"] = orders.amount
n_stray = N_TXN - len(orders)        # orders paid by other means: never linked to a card
stray = pd.DataFrame({
    "order_id": [f"O{N_TXN + i:05d}" for i in range(1, n_stray + 1)],
    "merchant_id": rng.choice(online, n_stray),
    "order_total": [money(np.exp(rng.normal(4.2, 0.8))) for _ in range(n_stray)],
    "ordered_at": [ts(rng.integers(0, 181)) for _ in range(n_stray)],
    "auth_code": None})
stray["shipped_at"] = (stray.ordered_at + pd.Timedelta(days=2)).dt.floor("h")
stray["delivered_at"] = (stray.shipped_at + pd.Timedelta(days=4)).dt.floor("h")
stray["delivery_status"] = "delivered"
ORDER_COLS = ["order_id", "merchant_id", "auth_code", "order_total", "ordered_at",
              "shipped_at", "delivered_at", "delivery_status"]
merchant_order = pd.concat([orders[ORDER_COLS], stray[ORDER_COLS]], ignore_index=True)

authorization = txn[["auth_id", "card_token", "merchant_id", "amount", "auth_code", "authorized_at"]].copy()
authorization["merchant_name"] = authorization.merchant_id.map(mrec.merchant_name)
clearing = pd.DataFrame({
    "arn": txn.arn, "card_token": txn.card_token, "merchant_id": txn.merchant_id,
    "descriptor": txn.merchant_id.map(mrec.descriptor), "amount": txn.cleared_amount,
    "auth_code": txn.auth_code.where(txn.clr_has_code), "cleared_at": txn.cleared_at})

# ---------------------------------------------------------------- claims
# strata of the clearing record a claim ends up linked to:
#   (auth link, order link) = key/fb for authorization, key/fb/none for order
txn["s_auth"] = np.where(txn.clr_has_code, "key", "fb")
txn["s_order"] = np.where(~has_order, "none",
                          np.where(txn.clr_has_code & txn.order_has_code, "key", "fb"))
txn["stratum"] = txn.s_auth + "/" + txn.s_order
excluded = set(violators) | {WORKED_IDX}
arn_to_idx = dict(zip(txn.arn, txn.index))


def stated_name(mid):
    name = mrec.merchant_name[mid]
    first, *rest = name.split()
    options = [name, first, name.lower(), first.lower(), name + " online",
               name.replace(" ", ""), first + " " + (rest[0][:3] if rest else "")]
    s = rng.choice(options)
    if rng.random() < 0.2 and len(s) > 5:             # a typo
        k = int(rng.integers(1, len(s) - 1))
        s = s[:k] + s[k + 1:]
    return s


def claim_row(i, when, name, amount=None):
    t = txn.loc[i]
    return pd.Series(dict(card_token=t.card_token, claimed_amount=amount or t.cleared_amount,
                          merchant_stated=name, claim_received_at=when))


def off_amount(x):
    return money(x * (1 + rng.choice([-1, 1]) * rng.uniform(0.015, 0.08)))


def secondary_ok(i):
    """The authorization and order links for this clearing record come out as designed."""
    clr = clearing.loc[i]
    a, how_a, _ = match(clr, authorization, "auth_id", "amount", "authorized_at")
    o, how_o, _ = match(clr, merchant_order, "order_id", "order_total", "ordered_at")
    want_o = None if txn.s_order[i] == "none" else "O" + txn.auth_id[i][1:]
    return (a == txn.auth_id[i] and o == want_o
            and how_a == ("key" if txn.s_auth[i] == "key" else "fuzzy"))


used = set()


def candidates(stratum, when, kind=None, lo=2, hi=90):
    ok = ((txn.stratum == stratum) & (txn.cleared_at <= when - pd.Timedelta(days=lo))
          & (txn.cleared_at >= when - pd.Timedelta(days=hi)) & ~txn.index.isin(used | excluded))
    if kind == "oneoff":
        ok &= txn.kind != "subscription"
    elif kind == "subscription":
        ok &= txn.kind == "subscription"
    pool = txn.index[ok].to_numpy()
    return rng.permutation(pool)


def make_clean(stratum, when, amount_off=False):
    for i in candidates(stratum, when, "oneoff")[:300]:
        name = stated_name(txn.merchant_id[i])
        amt = off_amount(txn.cleared_amount[i]) if amount_off else None
        arn, how, _, close = link_claim(claim_row(i, when, name, amt), clearing)
        if arn == txn.arn[i] and how == "name" and not close and secondary_ok(i):
            return i, name, amt or txn.cleared_amount[i], [i]
    return None


def make_amount_only(stratum, when, amount_off=False):
    for i in candidates(stratum, when, "oneoff")[:300]:
        name = rng.choice(GENERIC_NAMES)
        if similar(name, clearing.descriptor[i]) >= 0.6:
            continue
        amt = off_amount(txn.cleared_amount[i]) if amount_off else None
        arn, how, _, _ = link_claim(claim_row(i, when, name, amt), clearing)
        if arn == txn.arn[i] and how == "amount_only" and secondary_ok(i):
            return i, name, amt or txn.cleared_amount[i], [i]
    return None


def make_subscription(stratum, when, wrong):
    """A monthly charge: the linked record is the latest charge before the claim."""
    for j in candidates(stratum, when, "subscription", lo=1, hi=60)[:300]:
        series = txn[(txn.card_token == txn.card_token[j]) & (txn.merchant_id == txn.merchant_id[j])
                     & (txn.amount == txn.amount[j])].sort_values("cleared_at")
        before = series[series.cleared_at <= when]
        if len(before) < 2 or before.index[-1] != j:
            continue
        true_i = before.index[-2] if wrong else j
        if true_i in used or true_i in excluded:
            continue
        name = stated_name(txn.merchant_id[j])
        arn, how, _, close = link_claim(claim_row(true_i, when, name), clearing)
        if arn == txn.arn[j] and how == "name" and close and secondary_ok(j):
            return true_i, name, txn.cleared_amount[true_i], [true_i, j]
    return None


def make_missed(when):
    """A linkable claim that the rules cannot link: the stated amount is far off."""
    for i in candidates(rng.choice(["key/key", "key/fb"]), when, "oneoff")[:300]:
        amt = money(txn.cleared_amount[i] * rng.choice([0.6, 1.35, 1.5]))
        name = stated_name(txn.merchant_id[i])
        arn, how, _, _ = link_claim(claim_row(i, when, name, amt), clearing)
        if arn is None:
            return i, name, amt, [i]
    return None


# times: 102 claims before the worked example, the rest after it
def times(n, start, end):
    span = (end - start).total_seconds()
    return sorted(start + pd.Timedelta(seconds=float(s)) for s in rng.uniform(0, span, n))


N_EARLY, N_DUP = 102, 15
plan = (["clean"] * 346 + ["sub_right"] * 19 + ["sub_wrong"] * 5 + ["amount_only"] * 34
        + ["missed"] * 7 + ["unlinkable"] * 8)                    # + worked example + 15 dups
plan = list(rng.permutation(plan))
when_all = (times(N_EARLY, pd.Timestamp("2025-01-15"), WORKED_CLAIM_AT - pd.Timedelta(minutes=5))
            + times(len(plan) - N_EARLY, WORKED_CLAIM_AT + pd.Timedelta(minutes=5),
                    pd.Timestamp("2025-08-31 20:00")))
# early slots cannot be subscriptions disputes needing two charges before mid-February
early_ok = [k for k, s in enumerate(plan) if s not in ("sub_right", "sub_wrong")]
late_first = [k for k, s in enumerate(plan) if s in ("sub_right", "sub_wrong")]
slot_order = late_first + early_ok          # subscriptions get late times
slot_times = {}
late_times = when_all[N_EARLY:]
rng.shuffle(late_times)
early_times = list(when_all[:N_EARLY])
for k in late_first:                  # subscriptions charge January to June
    t = next(t for t in late_times if t < pd.Timestamp("2025-07-01"))
    late_times.remove(t)
    slot_times[k] = t
rest = early_times + late_times
rng.shuffle(rest)
for k in early_ok:
    slot_times[k] = rest.pop()

# strata for the 405 distinct linked clearing records (dups repeat key/key)
strata_pool = (["key/key"] * 255 + ["key/fb"] * 104 + ["key/none"] * 11
               + ["fb/fb"] * 33 + ["fb/none"] * 1)   # worked example takes one key/fb
strata_pool = list(rng.permutation(strata_pool))
linked_slots = [k for k, s in enumerate(plan) if s in ("clean", "sub_right", "sub_wrong", "amount_only")]
dup_slots = set(rng.choice([k for k in linked_slots if plan[k] == "clean"
                            and slot_times[k] > WORKED_CLAIM_AT
                            and slot_times[k] < pd.Timestamp("2025-08-15")], N_DUP, replace=False))
slot_stratum = {}
for k in dup_slots:
    strata_pool.remove("key/key")
    slot_stratum[k] = "key/key"
for k in [k for k in linked_slots if plan[k].startswith("sub")]:
    s = next(x for x in strata_pool if not x.endswith("none"))
    strata_pool.remove(s)
    slot_stratum[k] = s
for k in linked_slots:
    if k not in slot_stratum:
        slot_stratum[k] = strata_pool.pop()
assert not strata_pool
off_slots = set(rng.choice([k for k in linked_slots if plan[k] in ("clean", "amount_only")
                            and k not in dup_slots], 47, replace=False))

claims, truth = [], []


def add(i, name, amount, when, scenario, linked):
    claims.append(dict(card_token=txn.card_token[i] if i is not None else spare_cards.pop(),
                       claimed_amount=amount, merchant_stated=name, claim_received_at=when,
                       channel=rng.choice(CHANNELS, p=CHANNEL_P), scenario=scenario))
    truth.append(dict(arn=txn.arn[i] if i is not None else None,
                      auth_id=txn.auth_id[i] if i is not None else None,
                      order_id=None if i is None or txn.s_order[i] == "none" else "O" + txn.auth_id[i][1:]))
    used.update(linked)


# the worked example first
used.add(WORKED_IDX)
claims.append(dict(card_token=worked_card, claimed_amount=127.11, merchant_stated="Granite",
                   claim_received_at=WORKED_CLAIM_AT, channel="app", scenario="clean"))
truth.append(dict(arn=txn.arn[WORKED_IDX], auth_id="A02839", order_id="O02839"))

makers = {"clean": lambda k, w: make_clean(slot_stratum[k], w, k in off_slots),
          "amount_only": lambda k, w: make_amount_only(slot_stratum[k], w, k in off_slots),
          "sub_right": lambda k, w: make_subscription(slot_stratum[k], w, False),
          "sub_wrong": lambda k, w: make_subscription(slot_stratum[k], w, True),
          "missed": lambda k, w: make_missed(w)}
dup_sources = []
for k in slot_order:
    scenario, when = plan[k], slot_times[k]
    if scenario == "unlinkable":
        amount = money(np.exp(rng.normal(4.2, 0.8)))
        claims.append(dict(card_token=spare_cards.pop(), claimed_amount=amount,
                           merchant_stated=stated_name(rng.choice(online)),
                           claim_received_at=when, channel=rng.choice(CHANNELS, p=CHANNEL_P),
                           scenario=scenario))
        truth.append(dict(arn=None, auth_id=None, order_id=None))
        continue
    made, shift = None, 0
    while made is None:
        made = makers[scenario](k, when)
        if made is None:                      # no usable record near this time: move the claim
            shift += 1
            when = when + pd.Timedelta(days=3) if when > WORKED_CLAIM_AT + pd.Timedelta(days=4) \
                else when + pd.Timedelta(hours=6)
            when = min(when, pd.Timestamp("2025-08-31 22:00"))
            assert shift < 60, (scenario, k)
    i, name, amount, linked = made
    add(i, name, amount, when, scenario, linked)
    if k in dup_slots:
        dup_sources.append((i, amount, when))

# duplicate claims: the same purchase reported again through another channel
for i, amount, when in dup_sources:
    for _ in range(200):
        later = when + pd.Timedelta(days=float(rng.uniform(1, 12)))
        name = stated_name(txn.merchant_id[i])
        arn, how, _, close = link_claim(claim_row(i, later, name, amount), clearing)
        if arn == txn.arn[i] and how == "name" and not close:
            break
    else:
        raise RuntimeError("could not place duplicate")
    claims.append(dict(card_token=txn.card_token[i], claimed_amount=amount, merchant_stated=name,
                       claim_received_at=later, channel=rng.choice(CHANNELS, p=CHANNEL_P),
                       scenario="duplicate"))
    truth.append(dict(arn=txn.arn[i], auth_id=txn.auth_id[i],
                      order_id=None if txn.s_order[i] == "none" else "O" + txn.auth_id[i][1:]))

claims = pd.DataFrame(claims)
truth = pd.DataFrame(truth)
ids = ["C00001"] + [f"C{n:05d}" for n in rng.permutation(np.arange(2, len(claims) + 1))]
claims.insert(0, "claim_id", ids)
truth.insert(0, "claim_id", ids)
truth["scenario"] = claims.pop("scenario")
claims["claim_received_at"] = pd.to_datetime(claims.claim_received_at).dt.floor("min")
claims = claims.sort_values("claim_id").reset_index(drop=True)
truth = truth.sort_values("claim_id").reset_index(drop=True)
# truth for every clearing record too, so the secondary links can be scored
record_truth = pd.DataFrame({"claim_id": None, "arn": txn.arn, "auth_id": txn.auth_id,
                             "order_id": np.where(has_order, "O" + txn.auth_id.str[1:], None),
                             "scenario": "clearing_record"})
truth = pd.concat([truth, record_truth], ignore_index=True)


# ---------------------------------------------------------------- write
def write(df, name, time_cols):
    out = df.copy()
    for c in time_cols:
        out[c] = pd.to_datetime(out[c]).dt.strftime("%Y-%m-%d %H:%M")
    out.to_csv(HERE / name, index=False)
    print(f"{name:20s} {len(out):5d} rows")


write(authorization[["auth_id", "card_token", "merchant_id", "merchant_name", "amount",
                     "auth_code", "authorized_at"]], "authorization.csv", ["authorized_at"])
write(clearing, "clearing.csv", ["cleared_at"])
write(claims[["claim_id", "channel", "claim_received_at", "card_token", "claimed_amount",
              "merchant_stated"]], "crm_claim.csv", ["claim_received_at"])
write(merchant_order, "merchant_order.csv", ["ordered_at", "shipped_at", "delivered_at"])
write(truth, "truth_links.csv", [])
