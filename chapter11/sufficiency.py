"""Score whether the evidence is sufficient for a not-received claim (Listing 11.4)."""
from match import address_match, on_time
from requirements import NOT_RECEIVED as R


def sufficiency(facts, case, rules=R):
    score, gaps = 0.0, []
    if facts.get("delivered_to") is None:
        return 0.0, ["no delivery confirmation"], "insufficient"
    _, verdict = address_match(facts["delivered_to"], facts.get("ship_to"))
    if verdict == "match":
        score += 0.45
    elif verdict == "unit_differs":
        score += 0.10; gaps.append("unit differs")
    else:
        gaps.append("delivery address does not match")
    if facts.get("amount") == case.amount_cents:
        score += 0.10
    else:
        gaps.append("no order record for the amount")
    if facts.get("delivered_on") is None:
        gaps.append("no delivery date")
    elif on_time(facts["delivered_on"], case.expected_on, case.claimed_on):
        score += 0.20
    else:
        score += 0.05; gaps.append("delivered after expected date")
    attested = facts.get("attested")
    score += {"signed": 0.15, "photo": 0.10}.get(attested, 0.0)
    if attested not in ("signed", "photo"):
        gaps.append("no signature or photograph")
    if facts.get("delivered_to_channel") == "api":
        score += 0.10
    if verdict == "no_match":
        score = min(score, rules["veto"]["address_contradicted"])
    cut = rules["verdict"]
    label = ("sufficient" if score >= cut["sufficient"] else
             "borderline" if score >= cut["borderline"] else "insufficient")
    return round(score, 2), gaps, label
