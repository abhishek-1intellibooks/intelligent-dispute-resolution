"""Label pages by document type with a character n-gram classifier.

Merchants often send one file that merges an invoice, tracking history and an
email thread, and the same words (order, total, delivered) appear on all of
them. Character n-grams of three to five characters tolerate OCR errors better
than whole words: one wrong character spoils a word but only a few of its
n-grams. Pages the classifier is less than 60 percent sure of go to a person.

Trains on the pages in evidence_packets/pages.csv, tests on 1,000 held-out
pages. page_classifier() and classify() can be reused on real pages.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

HERE = Path(__file__).resolve().parent
PAGES = HERE / "evidence_packets" / "pages.csv"
ABSTAIN = 0.60          # below this the page goes to a person
N_TEST = 1000


def page_classifier():
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True,
                        sublinear_tf=True, min_df=2, max_features=60000),
        LogisticRegression(C=2.0, max_iter=3000))


def classify(model, texts, threshold=ABSTAIN):
    """(label, confidence, needs_person) for each page."""
    proba = model.predict_proba(texts)
    best = proba.argmax(axis=1)
    conf = proba[np.arange(len(texts)), best]
    return pd.DataFrame({"label": model.classes_[best], "confidence": conf.round(3),
                         "needs_person": conf < threshold})


def main():
    pages = pd.read_csv(PAGES, keep_default_na=False)
    rng = np.random.default_rng(7)
    test_idx = rng.choice(len(pages), N_TEST, replace=False)
    is_test = np.zeros(len(pages), bool)
    is_test[test_idx] = True
    train, test = pages[~is_test], pages[is_test]

    model = page_classifier().fit(train.text, train.doc_type)
    out = classify(model, test.text.tolist())
    out.index = test.index
    right = out.label == test.doc_type
    print(f"Page classifier: trained on {len(train):,} pages, "
          f"tested on {len(test):,} across {test.doc_type.nunique()} document types")
    print(f"  accuracy {right.mean():.1%}")
    for ch, g in right.groupby(test.channel):
        print(f"    {ch:<11} {g.mean():.1%}  ({len(g)} pages)")
    sure = ~out.needs_person
    print(f"  below {ABSTAIN:.0%} confidence, sent to a person: {out.needs_person.mean():.1%}")
    print(f"  accuracy on the remainder: {right[sure].mean():.1%}")
    print(pd.crosstab(test.doc_type, out.label, rownames=["true"],
                      colnames=["predicted"]).to_string())


if __name__ == "__main__":
    main()
