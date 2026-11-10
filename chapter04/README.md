# Chapter 4: Disputes Beyond Cards

On push rails such as ACH credits, wires, instant payments and P2P sends, the payer's bank cannot reverse a payment by right. It can only ask the receiving bank to send the money back, and how much comes back depends on how fast the request arrives. This chapter builds the rail adapter pattern for that problem. One shared case model (`RailCase`) is driven by a declarative `RailProfile` for each rail. A profile sets the rail's direction, its state machine, its clocks and the evidence a case must hold. A late recall is recorded as data instead of ending the case, and card events are rejected on push rails. **All amounts, durations and recovery rates are illustrative; all data are synthetic.**

## Files

| File | Purpose |
|---|---|
| `rail_adapters/__init__.py` | Package exports |
| `rail_adapters/base.py` | Listing 4.1: `RailProfile` (frozen declaration) and `RailCase` (state, clock, history, `apply`, `missing_evidence`) |
| `rail_adapters/profiles.py` | Listing 4.2: the `ACH_DEBIT`, `INSTANT` and `WIRE` profiles and the shared `PUSH_RECOVERY` transitions. **The P2P profile is a marked exercise** (`p2p_profile()` raises `NotImplementedError`; see Question 3) |
| `demo.py` | Listing 4.3: runs three claims and two checks |
| `recovery_curve.py` | The Figure 4.3 arithmetic: share recoverable = 0.5^(t / half-life) |
| `tests/test_rail_adapters.py` | pytest checks of clocks, late handling, rejection, evidence, the exercise stub and the curve |
| `requirements.txt` | Standard library only (pytest for the tests) |

The clocks are fixed durations that mirror the rules in `chapter02/timelines.yaml`. This chapter does not read that file.

## How to run

```bash
cd chapter04
python demo.py
python recovery_curve.py
python -m pytest -q tests
```

## Chapter artifact

`chapter04/rail_adapters/` gives one shared case model with ACH, wire and instant-payment profiles, and `demo.py` runs claims through it. The P2P profile is left for the reader to write.

## Results

`python demo.py` prints the following, which matches the book's output exactly:

```
ach-1   pull  -> RETURNED     ['on_time']
rtp-1   push  -> CLOSED_LOSS  ['on_time', 'on_time', 'on_time']
wire-1  push  -> LOSS_REVIEW  ['late', 'on_time']
missing: ['beneficiary_account', 'payer_statement']
rejected: 'chargeback_received' not allowed in REPORTED on rail 'instant'
```

`python recovery_curve.py` uses a $64,000 payment and a 6-hour half-life. It gives 89.1% ($57,018) after 1 h, $40,317 after 4 h and 6.2% ($4,000) after 24 h. These match the book's 89%, about $57,000, about $40,300, 6% and about $4,000. The tests pass (8 passed).
