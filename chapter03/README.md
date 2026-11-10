# Chapter 3: Anatomy of the Card Dispute Lifecycle

This chapter follows a card dispute through its stages: cardholder contact, inquiry, pre-dispute alert, chargeback, representment, pre-arbitration and arbitration. It pulls two levers: Deflect acts before the chargeback and Recover acts after it.

The folder encodes the lifecycle as a table-driven state machine. The machine refuses any action the rules do not allow, such as a refund once a chargeback exists, and records a missed response window as a default loss. A small module computes the break-even between contesting a claim and refunding it early. All amounts and fees are illustrative.

## Files

| File | Purpose |
|---|---|
| `card_state_machine.py` | Listing 3.1: `TRANSITIONS`, `CLOCK_DAYS` and the `CardDispute` dataclass |
| `demo.py` | Listing 3.2: three paths and one illegal event |
| `lifecycle_economics.py` | Contest-or-refund economics (the break-even win probability, Table 3.6 outcome costs and a decision function with a placeholder p) and annual contested/won volumes from `chapter01/disputes_sample.csv`. Also includes the **exercise stub** `clock_days_from_catalogue()` |
| `tests/test_card_state_machine.py` | Tests the paths, window edge cases, the no-refund-after-chargeback rule, the break-even and the volumes |
| `requirements.txt` | The state machine needs only the standard library; the economics module and the tests need pandas, PyYAML and pytest |

Cross-chapter inputs are `../chapter01/disputes_sample.csv` and `../chapter02/timelines.yaml`, so build Chapters 1 and 2 first.

## How to run

```bash
cd chapter03
python demo.py
python lifecycle_economics.py
python -m pytest -q tests
```

## Chapter artifact

`card_state_machine.py`, the card dispute lifecycle as a table-driven state machine, with `demo.py`.

## Results (as printed by the code)

```
deflected  -> DEFLECTED  due=None
contested  -> WON        due=None
missed     -> LOST       due=None
rejected: 'represent' is not allowed in SETTLED
```

This matches Table 3.5.

`lifecycle_economics.py` prints:

| Figure | Book | Code |
|---|---|---|
| Break-even win probability | about 21% | 20.9% |
| Table 3.6 outcome costs | $191 / $206 / $28 / $234 | $191 / $206 / $28 / $234 |
| Annual cases | 720,000 | 720,000 |
| Contested | 223,200 | 223,200 |
| Won | 93,744 | 93,744 |
| Lost | 129,456 | 129,456 |

The annual volumes come from the Chapter 1 data. All 10 tests pass.

## Exercise

The chapter's exercises (Question 4) replace `CLOCK_DAYS` with lookups against `chapter02/timelines.yaml`. `lifecycle_economics.clock_days_from_catalogue()` is left as a clearly marked stub that raises `NotImplementedError`. `catalogue_clocks()` shows the two catalogue entries to wire in: `visa_dispute_response` and `visa_pre_arbitration_response`, both 30 days.
