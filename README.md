# 🛍️ GOOPHER

**A unified conversational retail agent for JCPenney "Casual Dresses for Women",
delivered as a Chrome extension and powered by Google ADK + Gemini on Google
Cloud (free tier).**

GOOPHER lets a shopper discover dresses, check **real-time inventory**, and
manage **orders** (one at a time *or* in bulk) — across **channels** (web /
phone), **languages**, and **modalities** (text / voice / image / file) — all
while preserving conversation context.

> ℹ️ The product/order data is a **synthetic dataset modeled on** the JCPenney
> casual-dresses category. It is **not scraped** from jcpenney.com. See
> [`backend/data/jcpenney_casual_dresses.json`](backend/data/jcpenney_casual_dresses.json).

---

## ✨ Features → Requirements

| Feature | Where | Req |
|---|---|---|
| Chrome extension "GOOPHER" (MV3 side panel) | [`extension/`](extension/) | 2A |
| Customer authentication (JWT) | [`backend/app/auth/auth.py`](backend/app/auth/auth.py) | T1 |
| **ADK orchestrator** + 3 subagents | [`backend/app/agents/`](backend/app/agents/) | T2 |
| Memory agent — context across switches | [`backend/app/memory/memory_agent.py`](backend/app/memory/memory_agent.py) | T3 |
| Agent skills (inventory, orders) | [`backend/app/agents/skills/`](backend/app/agents/skills/) | T4 |
| **MCP tools** (inventory + order status) | [`backend/app/mcp/`](backend/app/mcp/) | T5 / 2A-1,2 |
| Gemini LLM (free tier) | `gemini-2.0-flash` | T6 |
| Google Cloud (Firestore + Cloud Run + Trace) | — | T7 / T14 |
| Multi-channel subagent (phone/web) | [`channel_agent.py`](backend/app/agents/channel_agent.py) | 2A-4 |
| Multi-lingual subagent | [`language_agent.py`](backend/app/agents/language_agent.py) | 2A-5 |
| Multi-modal subagent | [`modality_agent.py`](backend/app/agents/modality_agent.py) | 2A-6 |
| Individual **& high-volume** orders | [`order_tool.py`](backend/app/mcp/order_tool.py) + `/orders/bulk` | 3 |
| Evals | [`evals/`](evals/) | T8 |
| Unit tests | [`tests/`](tests/) | T9 |
| Observability (traces/logs/metrics) | [`telemetry.py`](backend/app/observability/telemetry.py) | T10 |
| Architecture writeup | [`ARCHITECTURE.md`](ARCHITECTURE.md) | T12 |
| Dockerized + Cloud Run | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | T14 / T16 |
| CI/CD (GitHub Actions) | [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) | T17 |

---

## 🚀 Quick start (local, no cloud, no API key)

The backend runs fully offline using SQLite + a deterministic fallback engine,
so you can try everything before touching Google Cloud.

```bash
# 1. Install (Python 3.11+)
python -m venv .venv && . .venv/Scripts/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Seed the local SQLite DB with JCPenney casual-dress data
python scripts/seed_data.py

# 3. Run the API
uvicorn backend.app.main:app --reload --port 8080
#   -> http://localhost:8080/healthz   /docs (Swagger UI)

# 4. Run tests + evals
pytest -q
python evals/run_evals.py
```

### Enable the real LLM (Gemini free tier)
```bash
# Get a free key: https://aistudio.google.com/app/apikey
export GOOGLE_API_KEY=AIza...        # PowerShell: $env:GOOGLE_API_KEY="AIza..."
uvicorn backend.app.main:app --reload --port 8080
```
With a key set, GOOPHER uses the **ADK + Gemini** path (real reasoning + tool
calling). Without one, it falls back to the deterministic engine.

---

## 🧩 Load the Chrome extension

1. Run the backend (above) so it's listening on `http://localhost:8080`.
2. (If needed) generate icons: `python extension/icons/generate_icons.py`.
3. Open **chrome://extensions** → enable **Developer mode** → **Load unpacked**
   → select the [`extension/`](extension/) folder.
4. Click the **GOOPHER** toolbar icon to open the side panel.
5. Sign in with the demo account: **`demo@goopher.app` / `demo`**.

Try:
- *"show me black casual dresses under $45"*
- *"is JCP-ANA-1001-NVY-S in stock?"*
- *"where is my order ORD-50002?"*  →  switch **Channel** to *Phone* and ask again
- *"Hola, ¿dónde está mi pedido ORD-50001?"*  (multi-lingual)
- Attach a 📎 CSV of order numbers → *"status for these"* (high-volume + multimodal)

> For production, set `API_BASE` in [`extension/config.js`](extension/config.js)
> to your Cloud Run URL.

---

## 🐳 Run with Docker

```bash
docker compose up --build      # serves on http://localhost:8080
```

---

## ☁️ Deploy to Google Cloud (free tier)

### One-time setup
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    firestore.googleapis.com cloudtrace.googleapis.com aiplatform.googleapis.com
gcloud firestore databases create --location=nam5      # native mode, free tier
```

### Deploy (manual)
```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_SERVICE=goopher-api
# then seed Firestore once:
DB_BACKEND=firestore GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID python scripts/seed_data.py
```

### Deploy (CI/CD — GitHub Actions, T17)
Push to `main`. The pipeline runs tests + evals, then (if the secrets below are
set) builds the image and deploys to Cloud Run. Add these **repository secrets**:

| Secret | Purpose |
|---|---|
| `GCP_PROJECT_ID` | your project id |
| `GCP_SA_KEY` | JSON key for a deployer service account |
| `GOOGLE_API_KEY` | Gemini free-tier key |
| `JWT_SECRET` | signing secret for auth tokens |

Repo: <https://github.com/sanikacentric/goopher_gcp.git>

```bash
git init && git add . && git commit -m "GOOPHER initial"
git branch -M main
git remote add origin https://github.com/sanikacentric/goopher_gcp.git
git push -u origin main
```

---

## 🗂️ Project layout
```
goopher/
├── backend/
│   ├── app/
│   │   ├── agents/         # ADK orchestrator + channel/language/modality subagents + skills
│   │   ├── auth/           # JWT customer auth (T1)
│   │   ├── db/             # SQLite/Firestore repository
│   │   ├── mcp/            # MCP server + inventory/order tools (T5)
│   │   ├── memory/         # conversational memory (T3)
│   │   ├── models/         # pydantic schemas
│   │   ├── observability/  # logging, tracing, metrics (T10)
│   │   ├── config.py       # env-driven settings
│   │   └── main.py         # FastAPI app
│   └── data/               # mock JCPenney casual-dress dataset
├── extension/              # Chrome extension "GOOPHER" (MV3)
├── evals/                  # behavioral evals (T8)
├── tests/                  # unit/integration tests (T9)
├── scripts/seed_data.py    # DB seeder
├── Dockerfile / docker-compose.yml / cloudbuild.yaml
├── .github/workflows/deploy.yml   # CI/CD (T17)
├── ARCHITECTURE.md         # architecture + flow (T12)
└── README.md
```

---

## 🔌 API
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | — | Authenticate, get JWT |
| GET | `/auth/me` | Bearer | Current customer |
| POST | `/chat` | Bearer | One conversational turn |
| POST | `/orders/bulk` | Bearer | High-volume order status |
| GET | `/healthz` | — | Liveness |
| GET | `/metrics` | — | Metrics (observability) |

Interactive docs at `/docs` when running.

---

## 🧪 Quality gates
- **Unit tests**: `pytest -q` — tools, auth, memory, subagents, orchestrator, API.
- **Evals**: `python evals/run_evals.py` — tool selection, groundedness, language,
  channel-safety; fails CI below 80%.
- **Observability**: every turn is traced (`trace_id` returned to the client),
  structured JSON logs, `/metrics` counters; flip `OTEL_EXPORTER=gcp` for Cloud Trace.

## ⚠️ Notes & disclaimers
- Synthetic JCPenney-style data; brand names used only for demo realism.
- Demo auth uses a seeded password; swap for Firebase Auth in production.
- All Google Cloud services chosen for their **always-free tiers**.
