"""Retrieve rule passages from rules_library.jsonl.

A similarity search finds text about the right topic, but the two networks
state similar requirements in similar words and each edition repeats most of
the last one. search_rules therefore filters on the case's reason family,
network and the edition in force on the date the case opened, and only then
ranks the remaining passages by TF-IDF similarity. Called without those keys
it searches the whole library, which is the baseline evaluate.py measures.
"""
import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

HERE = Path(__file__).resolve().parent
LIBRARY = HERE / "rules_library.jsonl"


@dataclass(frozen=True)
class Rule:
    id: str
    network: str            # "Network A", "Network B" or "any"
    reason_family: str      # e.g. "not_received", or "general"
    topic: str
    edition: str
    effective_from: date
    effective_to: date | None
    text: str

    def in_force(self, on):
        return self.effective_from <= on and (self.effective_to is None or on <= self.effective_to)


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


@lru_cache(maxsize=4)
def load_library(path=LIBRARY):
    rules = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            rules.append(Rule(row["id"], row["network"], row["reason_family"], row["topic"],
                              row["edition"], _as_date(row["effective_from"]),
                              _as_date(row["effective_to"]), row["text"]))
    return tuple(rules)


@lru_cache(maxsize=4)
def _index(path=LIBRARY):
    rules = load_library(path)
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform([r.text for r in rules])
    return rules, vectorizer, matrix


def search_rules(query, reason=None, network=None, on=None, k=3, path=LIBRARY):
    """Return the k passages most similar to the query.

    reason, network and on (a date) are keys: when given, passages that do not
    match them are removed before the similarity search, so that the search
    only ever chooses among passages that could apply to the case.
    """
    rules, vectorizer, matrix = _index(path)
    on = _as_date(on)
    keep = [i for i, r in enumerate(rules)
            if (reason is None or r.reason_family == reason)
            and (network is None or r.network == network)
            and (on is None or r.in_force(on))]
    if not keep:
        return []
    scores = linear_kernel(vectorizer.transform([query]), matrix[keep]).ravel()
    order = sorted(range(len(keep)), key=lambda j: (-scores[j], j))
    return [rules[keep[j]] for j in order[:k]]


def rules_for(reason, network, on, path=LIBRARY):
    """All passages for a reason family and network in force on a date (a pure lookup)."""
    on = _as_date(on)
    return [r for r in load_library(path)
            if r.reason_family == reason and r.network == network and r.in_force(on)]
