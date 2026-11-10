# Chapter 8: The Dispute Data Foundation

This chapter assembles one trustworthy case record from four sources that share no common key. It
generates four synthetic feeds (authorization, clearing, claim intake and merchant orders), lands
them unchanged in SQLite, and links each of 435 claims to its clearing record (fuzzy match on
merchant name), then to its authorization and merchant order (authorization code first, fallback
second). Every link records its method and confidence, uncertain cases are flagged for review, and a
truth file scores how good the links are. A quality report runs the five data-quality dimensions as
queries and shows the null-key trap that a naive pandas join walks into.

All data are synthetic and all amounts are illustrative.

## Files

| File | Purpose |
|---|---|
| `dispute_schema.sql` | SQLite schema: four source tables as received, `case_record` (Listing 8.1) with its partial unique index, `case_source_link`, `case_event`, and a `case_flat` view |
| `linking.py` | Linking rules (Listing 8.2): `norm`, `similar`, `link_claim`, `match` |
| `assemble_case.py` | Assembles one case per claim and writes everything to `dispute.db` (Listing 8.3) |
| `store.py` | `load_sources()` reads the feeds; `save()` builds `dispute.db` from the schema, converting dates to text and missing values to NULL |
| `make_sources.py` | Seeded generator for the four feeds and the truth file |
| `authorization.csv` | 3,000 authorizations (processor) |
| `clearing.csv` | 3,000 clearing records (network); 270 lack an authorization code |
| `crm_claim.csv` | 435 claims as the customer reported them |
| `merchant_order.csv` | 3,000 merchant orders; 909 lack an authorization code |
| `truth_links.csv` | True links: one row per claim (with `claim_id`), plus one row per clearing record giving its true authorization and order |
| `quality_report.py` | Quality rules (Table 8.4), the null-key trap, link scoring against the truth file (Table 8.5) and the worked-example record (Table 8.6) |
| `test_linking.py` | pytest tests for the rules, the partial unique index and the assembled counts |
| `dispute.db` | Created by `assemble_case.py` (not committed; rebuild it in a few seconds) |

## How to run

```bash
cd chapter08
python make_sources.py      # optional: the CSVs are committed; regenerates them identically
python assemble_case.py     # builds dispute.db
python quality_report.py    # Tables 8.4, 8.5, 8.6
python -m pytest -q
```

## Chapter artifact

`chapter08/dispute_schema.sql` and `assemble_case.py`: the case schema and the assembly of one
record from four sources.

## Results (as printed by the code)

`assemble_case.py`: `435 cases; {0: 15, 2: 12, 3: 408}`

| Check | Result | Book |
|---|---|---|
| Cases fully linked (clearing, authorization, order) | 408 of 435 | 408 of 435 |
| Clearing records with an auth code | 2,730 of 3,000 | 2,730 of 3,000 |
| Merchant orders with an auth code | 2,091 of 3,000 | 2,091 of 3,000 |
| Clearing dated before its authorization | 6 | 6 |
| Linked claims whose amount differs by more than 1% | 47 of 420 | 47 of 420 |
| Live cases sharing an ARN / duplicate claims | 0 / 15 | 0 / 15 |
| Null-key trap: clearing-to-order join rows | 8,084 naive versus 1,893 correct | 8,084 versus 1,893 |

| Link | Linked | By key or name | By fallback | Unlinked | Accuracy |
|---|---|---|---|---|---|
| Claim to clearing | 420 of 435 | 386 | 34 | 15 | 98.8% (415 of 420) |
| Clearing to authorization | 420 of 420 | 386 | 34 | 0 | 100% |
| Clearing to order | 408 of 420 | 270 | 138 | 12 | 100% |

Recall: 415 of the 427 linkable claims were linked correctly (97.2%). All 5 wrong links are among the 39
cases flagged for review (24 ambiguous plus 15 unlinked). The worked example (claim C00001, "Granite",
$127.11) becomes CASE00103: clearing by name at 0.78 (GRANITETOYS*5274), authorization A02839 by key
(code 5006F2), order O02839 by fallback at 0.70, delivered 11 March, nine days before the claim.

These figures match the book exactly because the generator is built to produce them. It picks a
scenario for each claim (clean name match, amount-only, ambiguous subscription, missed, unlinkable,
duplicate) and checks it with the rules in `linking.py`. The records themselves are random. As the
chapter warns, real descriptors are messier and real fallbacks make mistakes, so recompute these
figures on your own data.

Note: with numpy 2.x and pandas 2.3 the scripts may print a numpy `DeprecationWarning` about the
"generic" timedelta unit. It comes from inside pandas and does not affect the results.
