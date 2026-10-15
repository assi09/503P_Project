# Agentic Fitbit Data Analysis

EECE 503N/798S course project (Fall 2026) — Karim Assi, Jad Harakeh.

Fitbit shows daily scores, but answering questions like *"why was my sleep worse this month?"* or
*"did my new training routine change my recovery?"* still means scrolling through screens and comparing
numbers by hand. This project builds an agent that analyzes months of a user's Fitbit data, decides
which metrics and time windows are worth investigating, and reports trends, changes and relationships —
with every insight backed by a computed statistic the user can inspect.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI service: data ingestion, analysis tools, agent, API |
| `mobile/` | Expo (React Native) app |
| `eval/` | Evaluation suite: synthetic data, baselines, adversarial tests |
| `docs/` | Architecture, API, failure matrix, threat model |

## Data and privacy

Personal Fitbit exports (Google Takeout) are **never committed**. Place an export under `data/raw/`
(git-ignored) to run the pipeline locally.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"
pytest backend
```
