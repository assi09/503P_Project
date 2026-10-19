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
| `mobile/` | Expo (React Native) app for iOS, Android and web |
| `eval/` | Evaluation suite: synthetic data, baselines, adversarial tests |
| `docs/` | Architecture, API, failure matrix, threat model |

## Contributing

Work goes through short-lived branches and pull requests into a protected `main`. See
[AGENTS.md](AGENTS.md) for the workflow, the verification checklist and the project's rules; AI
coding agents read it automatically (`CLAUDE.md` points to it).

## Data and privacy

Personal Fitbit exports (Google Takeout) are **never committed**. Place an export under `data/raw/`
(git-ignored) to run the pipeline locally.

## Setup

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"
pytest backend
```

### Mobile app

Requires Node 22. The app runs on mock data until the backend API exists; set
`EXPO_PUBLIC_API_URL` to point it at a running backend.

```bash
cd mobile
npm install
npm start             # then scan the QR code with the Expo Go app (iOS/Android)
npm run web           # web version in the browser
npm run lint && npm run typecheck && npm test
```

To try it on a phone that is not on the same Wi-Fi (for example a friend's), run
`npx expo start --tunnel` and have them scan the QR code with Expo Go.
