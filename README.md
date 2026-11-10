# Intelligent Dispute Resolution: Companion Repository

Code, synthetic data and notebooks for the book **Intelligent Dispute Resolution**.
Each chapter has its own folder (`chapter01/` to `chapter16/`). `CHAPTER.md` holds the chapter's text and figures, and `README.md` explains how to run the code and which results it reproduces.

> All data in this repository are synthetic. Every amount, fee, rate and result is illustrative.
> Rules and deadlines in `chapter02/timelines.yaml` are stated as of October 2026. Check them against their cited sources before you rely on them.

## Chapters

| # | Chapter | Read the chapter | Code and data | Chapter artifact |
|---|---------|------------------|---------------|------------------|
| 1 | Understanding the Dispute Landscape in Modern Payments | [CHAPTER.md](chapter01/CHAPTER.md) | [chapter01](chapter01/) | Baseline Dispute Ledger (`explore.ipynb`) |
| 2 | Understanding the Rules of the Game: Regulation and Network Frameworks | [CHAPTER.md](chapter02/CHAPTER.md) | [chapter02](chapter02/) | The rules as data (`timelines.yaml`, `clocks.py`) |
| 3 | Anatomy of the Card Dispute Lifecycle | [CHAPTER.md](chapter03/CHAPTER.md) | [chapter03](chapter03/) | Card dispute state machine (`card_state_machine.py`) |
| 4 | Disputes Beyond Cards | [CHAPTER.md](chapter04/CHAPTER.md) | [chapter04](chapter04/) | Rail adapter package (`rail_adapters/`) |
| 5 | Dispute Operations: People, Process, Performance | [CHAPTER.md](chapter05/CHAPTER.md) | [chapter05](chapter05/) | KPI dashboard (`ops_kpi_dashboard.ipynb`) |
| 6 | Friendly Fraud and First-Party Misuse | [CHAPTER.md](chapter06/CHAPTER.md) | [chapter06](chapter06/) | First-party signals (`first_party_signals.py`) |
| 7 | The Business Case for Dispute Transformation | [CHAPTER.md](chapter07/CHAPTER.md) | [chapter07](chapter07/) | Business case model (`business_case.xlsx`) |
| 8 | The Dispute Data Foundation | [CHAPTER.md](chapter08/CHAPTER.md) | [chapter08](chapter08/) | Unified case record (`assemble_case.py`) |
| 9 | ML for Classification and Triage | [CHAPTER.md](chapter09/CHAPTER.md) | [chapter09](chapter09/) | Triage service (`triage_service.py`) |
| 10 | Outcome Prediction and Recovery Optimization | [CHAPTER.md](chapter10/CHAPTER.md) | [chapter10](chapter10/) | Contest-or-accept decision (`fight_or_accept.py`) |
| 11 | Document Intelligence and Evidence Automation | [CHAPTER.md](chapter11/CHAPTER.md) | [chapter11](chapter11/) | Evidence pipeline |
| 12 | Generative AI for Dispute Operations | [CHAPTER.md](chapter12/CHAPTER.md) | [chapter12](chapter12/) | Case summarizer and representment drafter |
| 13 | Agentic AI and Autonomous Resolution | [CHAPTER.md](chapter13/CHAPTER.md) | [chapter13](chapter13/) | Dispute agent (`agent.py`) |
| 14 | Cloud-Native Dispute Platform Architecture | [CHAPTER.md](chapter14/CHAPTER.md) | [chapter14](chapter14/) | Event-driven platform and deployment (`deploy/`) |
| 15 | Security, Compliance and Responsible AI | [CHAPTER.md](chapter15/CHAPTER.md) | [chapter15](chapter15/) | Governance controls (`audit.py`, `fairness.py`, `model_card.yaml`) |
| 16 | Case Studies and the Future of Disputes | [CHAPTER.md](chapter16/CHAPTER.md) | [chapter16](chapter16/) | Capstone end-to-end run (`run_month.py`) |

## Getting started

```bash
git clone https://github.com/abhishek-1intellibooks/intelligent-dispute-resolution.git
cd intelligent-dispute-resolution
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd chapter01
jupyter notebook explore.ipynb
```

You need Python 3.11 or later. No GPU or cloud account is required.
Chapters 12 and 13 run against a deterministic offline model by default. A hosted model is used only if you set the environment variables described in `chapter12/README.md`.

Run each script from inside its chapter folder. Later chapters read files from earlier ones, such as `chapter01/disputes_sample.csv` and `chapter02/timelines.yaml`, so keep the folder layout as it is.
