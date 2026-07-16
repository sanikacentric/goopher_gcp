# 🛍️ GOOPHER

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![CI](https://github.com/sanikacentric/goopher_gcp/actions/workflows/deploy.yml/badge.svg)](https://github.com/sanikacentric/goopher_gcp/actions/workflows/deploy.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**A unified conversational retail agent for JCPenney "Casual Dresses for Women",
delivered as a Chrome extension and powered by Google ADK + Gemini on Google
Cloud (free tier).**

> 🔓 **Open source (Apache-2.0).** GOOPHER runs locally with **zero secrets** —
> SQLite, simulated payments, and simulated order email out of the box. See
> [CONTRIBUTING.md](CONTRIBUTING.md) to get started and
> [SECURITY.md](SECURITY.md) before deploying your own instance.

GOOPHER lets a shopper discover dresses, check **real-time inventory**, and
manage **orders** (one at a time *or* in bulk) — across **channels** (web /
phone), **languages**, and **modalities** (text / voice / image / file) — all
while preserving conversation context.

> ℹ️ The product/order data is a **synthetic, representative dataset** spanning
> two departments (women's casual clothing + food/snacks). It is **not scraped**
> from any retailer; brand names are used only for demo realism. See
> [`backend/data/goopher_catalog.json`](backend/data/goopher_catalog.json).

---

## ✨ Features → Requirements

| Feature | Where | Req |
|---|---|---|
| Chrome extension "GOOPHER" (MV3 side panel) | [`extension/`](extension/) | 2A |
| Customer authentication (JWT) | [`backend/app/auth/auth.py`](backend/app/auth/auth.py) | T1 |
| **ADK orchestrator** + 3 subagents | [`backend/app/agents/`](backend/app/agents/) | T2 |
| Memory agent — context across switches | [`backend/app/memory/memory_agent.py`](backend/app/memory/memory_agent.py) | T3 |
| Agent skills (inventory, orders) | [`backend/app/agents/skills/`](backend/app/agents/skills/) | T4 |
| **In-process function tools** (inventory + order status) | [`backend/app/tools/`](backend/app/tools/) | T5 / 2A-1,2 |
| Gemini LLM (free tier) | `gemini-2.5-flash` | T6 |
| Google Cloud (Firestore + Cloud Run + Trace) | — | T7 / T14 |
| Multi-channel subagent (phone/web) | [`channel_agent.py`](backend/app/agents/channel_agent.py) | 2A-4 |
| Multi-lingual subagent | [`language_agent.py`](backend/app/agents/language_agent.py) | 2A-5 |
| Multi-modal subagent | [`modality_agent.py`](backend/app/agents/modality_agent.py) | 2A-6 |
| **Vision subagent** — camera "see it, shop it" (Gemini Vision), **confirm-before-charge** | [`vision_agent.py`](backend/app/agents/vision_agent.py) + `/vision` | 2A-6 |
| **Shopping Advisor** — explicit **ReAct** (`PlanReActPlanner`), read-only | [`advisor_agent.py`](backend/app/agents/advisor_agent.py) + `/advise` | T2 |
| **Agent Skill Registry** — named skills agents pick from | [`agent_skill_registry.py`](backend/app/agents/skills/agent_skill_registry.py) + `/skills` | T4 |
| **Agent Harness** (scaffolding) — common runtime for ALL agents | [`harness/`](backend/app/agents/harness/) | T2 |
| **Checkout** — single + bulk, structured transactional gate | [`checkout_tool.py`](backend/app/tools/checkout_tool.py) | 4 |
| **Order management** — 9-stage fulfillment → `ORDER_PLACED` | [`order_mgmt_tool.py`](backend/app/tools/order_mgmt_tool.py) | 5 |
| **Bulk order from an uploaded file** | [`orchestrator.py`](backend/app/agents/orchestrator.py) `_try_file_bulk_order` | 3 |
| **Cart / orders panel** in the extension | [`extension/`](extension/) + `/orders/mine` | 2A |
| **Phone channel = mobile-device simulator** | [`extension/sidepanel.*`](extension/) | 2A-4 |
| **Contextual ordering** ("order it" / "the above item") | [`orchestrator.py`](backend/app/agents/orchestrator.py) + `get_last_viewed` | 4 |
| **Self-service GenAI front end** (chat) | [`extension/`](extension/) + `/chat` | 4 |
| **Self-healing Guardian** (circuit breaker, failover, chaos demo) | [`guardian.py`](backend/app/agents/guardian.py) + `/dev` | T10 |
| **RSI — recursive self-improvement** (CriticAgent: learns from 👎 feedback) | [`critic_agent.py`](backend/app/agents/critic_agent.py) + `/critic/*`, `/dev` | T10 |
| **Developer portal** — live end-to-end flow visualizer | [`static/dev_portal.html`](backend/app/static/dev_portal.html) + `/dev` | T10 |
| **Single-user lockdown** (email allowlist + master pw, fail-closed) | [`auth.py`](backend/app/auth/auth.py), `config.allowed_emails` | T1 / Sec |
| **Abuse protection** (rate limiting + request-size limits, DoS) | [`middleware.py`](backend/app/middleware.py) | Sec |
| Individual **& high-volume** orders | [`order_tool.py`](backend/app/tools/order_tool.py) + `/orders/bulk` | 3 |
| Evals | [`evals/`](evals/) | T8 |
| Unit tests (113 passing) | [`tests/`](tests/) | T9 |
| Observability (traces/logs/metrics + `/version`) | [`telemetry.py`](backend/app/observability/telemetry.py) | T10 |
| README | this file | T11 |
| Architecture writeup | [`ARCHITECTURE.md`](ARCHITECTURE.md) | T12 |
| Production-grade, Cloud-deployable | Dockerfile + Cloud Run | T14 |
| Comments explaining logic | throughout | T15 |
| Dockerized + Cloud Run | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | T14 / T16 |
| CI/CD (GitHub Actions) | [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) | T17 |

---

## 🆕 This session — what changed

**New agents & infrastructure**
- **🧠 Shopping Advisor — explicit ReAct.** A new, isolated agent
  ([`advisor_agent.py`](backend/app/agents/advisor_agent.py), `POST /advise`) on
  ADK's **`PlanReActPlanner`** — it visibly **plans → acts over tools → reasons →
  recommends** and is **read-only** (never places an order). Tap **🧠** in the
  extension for a recommendation plus a collapsible ReAct reasoning panel. This
  gives GOOPHER **two agent styles on the same Gemini 2.5 Flash**: native
  function-calling agents for transactions, explicit ReAct for advice. See
  [`ARCHITECTURE.md` §5f](ARCHITECTURE.md).
- **🗂 Agent Skill Registry.** Skills are registered once in
  [`agent_skill_registry.py`](backend/app/agents/skills/agent_skill_registry.py)
  (single source of truth); agents **pick skills by name**, each skill carries a
  `read_only` flag, and **`GET /skills`** exposes the live capability map. The
  read-only advisor composes **only read-only skills** (asserted in code) so it can
  never get a checkout tool. See [`ARCHITECTURE.md` §5g](ARCHITECTURE.md).
- **🧰 Agent Harness (scaffolding).** One **common runtime** —
  [`harness/`](backend/app/agents/harness/) — wraps **every** agent (orchestrator +
  4 workers **and** the advisor): build → session → run-loop → collect → resilience
  → structured result. Replaces the boilerplate that was copy-pasted in two places.
  See [`ARCHITECTURE.md` §5h](ARCHITECTURE.md).

**Enterprise orders & notifications**
- **📊 Excel / CSV bulk orders.** Upload an enterprise purchase order
  (`.xlsx`/`.csv` with `product_name` / `sku` / `order_quantity` columns) → GOOPHER
  parses it with **openpyxl**, matches every line to the live catalog (by **SKU
  first, then name** — never substitutes), **previews the cart and asks "please
  confirm,"** then places **one structured bulk order** with the exact quantities.
  An `.xlsx` is a binary ZIP, so it's parsed properly — not decoded as text. The
  Confirm button re-sends the resolved `SKU=qty` lines, so the file is never
  re-uploaded. See [`ARCHITECTURE.md` §5d](ARCHITECTURE.md).
- **📧 Order-confirmation email on every order.** Single or bulk, via **text /
  voice / phone / camera vision / Excel** — every placed order composes a receipt
  in the shopper's language ([`email_tool.py`](backend/app/tools/email_tool.py)).
  It's **best-effort and never blocks checkout** (wrapped in try/except), and
  pluggable: **Resend** (free tier) or **SMTP**. **Defaults to a clearly-labelled
  simulated mode** — nothing is sent until you configure a transport. See
  [Order-confirmation email](#-order-confirmation-email-optional) to enable real
  delivery, and [`ARCHITECTURE.md` §5m](ARCHITECTURE.md) for the internals.

**Fixes & parity**
- **📷 Vision now asks "please confirm" before charging** — camera orders preview a
  cart and wait for confirmation, exactly like text and voice (no more
  charge-on-capture). Confirm re-places the **resolved SKU** — never a substitute.
- **🗣️ Voice captures the WHOLE sentence** — the mic is kept warm so the first
  words aren't dropped, and a spoken/typed **"confirm order"** now resolves the
  pending checkout (instead of being treated as a brand-new order).
- **🧠 Advisor reliability + context** — fixed the "plan but no answer" stall
  (`thinking_budget=0` + a grounded synthesis fallback), and it now recommends from
  your **most recent order's department and price** (e.g. a $17.99 toy → other toys
  ~≤ $18), not a hardcoded "snacks under $4".

---

## 🎥 Multimodal & multi-channel highlights

- **Camera "see it, shop it" (Gemini Vision).** Point the camera at a real toy or
  food item and **say** or type your request. The [vision subagent](backend/app/agents/vision_agent.py)
  recognizes it with **Gemini Vision on Vertex AI**, resolves it to a real catalog
  product (never substitutes), and either answers the price or **previews the order
  and asks "please confirm"** before charging — through the same structured
  checkout gate as a typed order (parity with text & voice).
- **Voice in + speaker out.** Speak the command; GOOPHER reads the answer aloud.
- **Durable session memory (T3).** Every turn **loads prior context** at the start
  and **persists the new turn** at the end (`MEMORY · session updated` in `/dev`)
  — to **Firestore** in the cloud (durable + shared across Cloud Run instances,
  surviving scale-to-zero). So "is it in navy?" → "order it" resolves *"it"*
  correctly, and language/channel carry across turns (start Web/English, continue
  Phone/Spanish, same thread).
- **Phone (Voice) channel renders a mobile-device simulator** (bezel, status bar,
  home indicator) with all the same features as Web.
- **Cart / orders panel.** A 🛒 button in the extension header shows everything
  already ordered (`GET /orders/mine`); the badge updates after each checkout.
- **Bulk order from an uploaded file.** Attach an `order.txt`
  (`order - 15 oreo cookies`, `order -20 balls`, SKUs, `lego x1`, …) and GOOPHER
  parses it into **one structured bulk order with per-line quantities**; unknown
  items are skipped and reported, never substituted.
- **The transactional gate.** Checkout is always handled deterministically
  (structured cart → simulated payment → `ORDER_PLACED` → staged receipt) in
  *every* path — the LLM orchestrates and converses, but never executes the
  purchase. See [`ARCHITECTURE.md` §5b](ARCHITECTURE.md).
- **🛡️ Self-healing Guardian.** A separate, isolated agent that wraps work in a
  resilience policy — **circuit breaker · retry-with-backoff · failover ·
  self-repair · health probes**. The `/dev` portal has a live **health strip**
  and **chaos buttons** ("Kill Vertex"): break a subsystem on demand and watch it
  self-heal. The recovery is a **4-step loop** streamed live as a HEAL card:
  1. **🔎 DETECT** — catch the failure, mark the component 🟠, bump the breaker.
  2. **🧠 DIAGNOSE** — classify the fault against a playbook (root cause).
  3. **🔧 REMEDIATE** — self-repair (e.g. re-seed) → retry with backoff → fail
     over, so the **customer is still served**.
  4. **✅ VERIFY** — 🟢 if recovered on the primary, 🟠 if serving via failover.

  Wrapped by a **⚡ circuit breaker** (open after N failures, serve the fallback)
  and a **🔄 background probe** that **heals forward** — restores the primary and
  closes the circuit once the fault clears, autonomously. To find the buttons:
  open `/dev` → the **🛡️ Guardian** panel under the legend → **💥 Kill Vertex** →
  **▶ Vertex** → **✅ Restore all**. See [`ARCHITECTURE.md` §5e](ARCHITECTURE.md)
  and the **[demo script](DEMO.md)**.

> 💼 **Business case:** **[BUSINESS-CASE.pptx](BUSINESS-CASE.pptx)** — a 9-slide
> consulting deck (current state → problem → loss → requirement → GOOPHER solution
> → ROI → pilot) for the stakeholder conversation.
>
> 🎬 **Presenting this?** Use the ready-to-deliver deck **[PRESENTATION.pptx](PRESENTATION.pptx)**
> (12 slides, speaker notes embedded) with the **[SPEAKER-NOTES.md](SPEAKER-NOTES.md)**
> one-pager. **[PRESENTATION.md](PRESENTATION.md)** is the interactive slide outline,
> **[DEMO.md](DEMO.md)** is the word-for-word walkthrough, and
> **[QUESTION-ANSWER.md](QUESTION-ANSWER.md)** is the Q&A bank for technical and
> stakeholder questions, and **[TRADEOFFS.md](TRADEOFFS.md)** documents every design
> trade-off (options considered → chosen → why).

---

## 🧠 Fulfillment · agent state · loop prevention

**Fulfillment (order-management) pipeline.** The 9-stage pipeline (Validate →
Inventory Check → `ORDER_PLACED` → Confirm → Warehouse → Ship → Track → Deliver →
Invoice) is the **`order_management_agent`'s** capability (its `fulfillment` skill
+ `run_fulfillment` tool). For a real purchase it runs **deterministically the
moment payment succeeds** (from the checkout gate), not as an LLM step — the agent
*owns* it, deterministic code *runs* it. See [`ARCHITECTURE.md` §5i](ARCHITECTURE.md).

**Agent state.** State is **centralized & shared by `session_id`**, not per-agent:
a single **session memory** store (turns + working-memory `facts`), durable in
**Firestore** in the cloud, that every conversational agent reads/writes; a
parallel **ADK session** under the same key (via the harness); plus isolated
Guardian health state and the durable business repository. **Vision and the
Advisor are stateless** — they pull "memory" from tools (e.g. order history). See
[`ARCHITECTURE.md` §5j](ARCHITECTURE.md).

**Loop prevention (structural, not prompted).** Agent loops can't form because:
the orchestrator uses **agent-as-tool** (workers return results, can't transfer
control back → no A→B→A cycle); workers hold **only function tools** (no nested
agents → bounded depth); each turn is a **single pass**; the **transactional path
is deterministic** (outside the loop); **retries are bounded** (1, or 2 for the
read-only advisor); failures **degrade once** to the deterministic engine; and the
Guardian's **circuit breaker** stops retry storms. The only planner-based agent
(the advisor) is capped with a guaranteed-termination fallback. See
[`ARCHITECTURE.md` §5k](ARCHITECTURE.md).

**RSI — recursive self-improvement (CriticAgent).** Two layers of self-healing:
the Guardian heals the **infrastructure**; the **CriticAgent heals the
behaviour**. Click **👎 Teach GOOPHER** on a weak answer → it critiques its own
failure with **Gemini-as-judge** (gemini-2.5-flash on Vertex), writes a
**confidence-gated corrective lesson**, stores it, and **retrieves it via RAG** to
improve the next similar answer — **no retraining, no redeploy**. Isolated: the
lesson injection into `/chat` is additive and a strict no-op when nothing matches.
Watch it in `/dev` (🔎 DETECT → 🧠 JUDGE → 💡 LESSON) and reset between demos with
the `/dev` **🧹 Reset lessons** button. Production vision: CCAI Insights + Vertex
Embeddings + Vector Search, run as a Cloud Run Job every 15 min via Cloud
Scheduler. See [`ARCHITECTURE.md` §5l](ARCHITECTURE.md).

---

## 🤖 LLM models

| Model | Provider | Where | Used for |
|---|---|---|---|
| **`gemini-2.5-flash`** | Google (Gemini) | **Vertex AI** (cloud) / AI Studio (local) | The **primary model** — ADK orchestrator + worker sub-agents, grounded replies, multilingual phrasing, **and camera Vision** (it's natively multimodal) |
| **`gpt-4o-mini`** | OpenAI | local only | Swappable alternate (`LLM_PROVIDER=openai`) for phrasing + a vision fallback |

- **Production runs purely on `gemini-2.5-flash` via Vertex AI** (`LLM_PROVIDER=gemini`,
  `USE_VERTEXAI=true`, **no OpenAI key** in the cloud) — one model does multi-agent
  reasoning, language, *and* vision.
- **No LLM at all** for: the deterministic intent router, the language/channel/
  modality pre-processing, the transactional checkout gate, and the Guardian
  self-healing. The LLM is used for understanding + phrasing, never to execute a
  transaction.
- Vision uses the same `gemini-2.5-flash` with `thinking_budget=0` (a short
  classification — see `LEARNINGS.md §3.16`).
- **Two agent styles on the one model.** The production workers are **native
  function-calling `LlmAgent`s** (the ReAct paradigm via Gemini's structured
  tool-calling — reliable, used for the transactional path). A separate, isolated
  **🧠 Shopping Advisor** (`advisor_agent.py`, `POST /advise`) uses ADK's
  **explicit `PlanReActPlanner`** to visibly **plan → act → reason → recommend**
  (read-only — it never places an order). Tap the **🧠** button in the extension
  to see the live ReAct reasoning panel. See [`ARCHITECTURE.md` §5f](ARCHITECTURE.md).

---

## 🚀 Quick start (local, no cloud, no API key)

The backend runs fully offline using SQLite + a deterministic fallback engine,
so you can try everything before touching Google Cloud.

```bash
# 1. Install (Python 3.11+)
python -m venv .venv && . .venv/Scripts/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Seed the local SQLite DB with the clothing + food catalog
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

## 📧 Order-confirmation email (optional)

Every placed order — single or bulk, from **text / voice / phone / camera vision
/ Excel upload** — sends a confirmation receipt in the shopper's language.

**By default this runs in SIMULATED mode: no credentials, no mail server, and
nothing actually sent.** The email is composed, written to the logs, and shown in
the reply, so the whole flow is demonstrable out of the box. This is deliberate —
the public repo ships **no real email address and no mail credentials**.

Sending is **best-effort and never blocks checkout** — if a transport is
misconfigured or down, the order still completes
([`email_tool.py`](backend/app/tools/email_tool.py) wraps it in try/except).

### Enabling real delivery

There is a provision to send real email whenever you want it. Set **`NOTIFY_EMAIL`**
(the recipient) plus **one** transport — the first one configured wins:

| | Variables | Notes |
|---|---|---|
| **Resend** | `RESEND_API_KEY` | Free tier. The test sender `onboarding@resend.dev` needs no domain verification, but only delivers to your Resend account's own address — so set `NOTIFY_EMAIL` to that same address. |
| **SMTP** | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | e.g. Gmail with a 16-char App Password. |
| **(none)** | — | **Simulated mode** — the default. |

**Locally** — in `.env` (gitignored, never committed):
```bash
NOTIFY_EMAIL=you@example.com
RESEND_API_KEY=re_xxx            # or the SMTP_* set
```

**On Cloud Run via CI** — add `NOTIFY_EMAIL` and `RESEND_API_KEY` as GitHub
repository secrets (**Settings → Secrets and variables → Actions**). The deploy
reads them; with neither set it falls back to `orders@example.com` and stays in
simulated mode. Never hardcode either into `deploy.yml` or commit them.

> 🔒 Keep the recipient address in a **secret**, not a plain variable — secrets
> are encrypted, masked in logs, and are **not exposed to pull requests from
> forks**, so a malicious fork PR cannot read them.

See [`ARCHITECTURE.md` §5m](ARCHITECTURE.md) for the transport-selection logic.

---

## 🧩 Load the Chrome extension

1. Run the backend (above) so it's listening on `http://localhost:8080`.
2. (If needed) generate icons: `python extension/icons/generate_icons.py`.
3. Open **chrome://extensions** → enable **Developer mode** → **Load unpacked**
   → select the [`extension/`](extension/) folder.
4. Open the **storefront** at **http://localhost:8080/** to browse the two
   departments (Clothing + Food).
5. Click the **GOOPHER** toolbar icon to open the side panel (it works on the
   storefront and any page).
6. Sign in with the demo account: **`demo@goopher.app` / `demo`**.

Try (clothing **and** food):
- *"show me black casual dresses under $45"*
- *"do you have barbecue chips?"* · *"how much are oreos?"*
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
│   └── data/               # mock catalog: clothing + food (goopher_catalog.json)
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
| POST | `/chat` | Bearer | One conversational turn (text/voice/file) |
| POST | `/vision` | Bearer | Camera "see it, shop it" — Gemini Vision recognize → price/order |
| GET | `/orders/mine` | Bearer | The customer's orders (cart/orders panel) |
| POST | `/orders/bulk` | Bearer | High-volume order status |
| GET | `/healthz` | — | Liveness |
| GET | `/version` | — | Build marker (which code is deployed) |
| GET | `/metrics` | — | Metrics (observability) |
| GET | `/dev/health` | — | Guardian component health (self-healing strip) |
| POST | `/dev/chaos` | — | Inject/clear a chaos fault (demo control) |
| POST | `/dev/heal-demo` | — | Run a synthetic transaction → watch it self-heal |

Interactive docs at `/docs` when running.

---

## 🧪 Quality gates
- **Unit tests**: `pytest -q` — tools, auth, memory, subagents, orchestrator, API.
- **Evals**: `python evals/run_evals.py` — tool selection, groundedness, language,
  channel-safety; fails CI below 80%.
- **Observability**: every turn is traced (`trace_id` returned to the client),
  structured JSON logs, `/metrics` counters; flip `OTEL_EXPORTER=gcp` for Cloud Trace.

## ⚠️ Notes & disclaimers
- Synthetic JCPenney-style data; brand names used only for demo realism. GOOPHER
  is **not affiliated with, endorsed by, or sponsored by** JCPenney or any brand
  named in the demo catalog.
- **Payments are simulated** — `process_payment` always succeeds and moves no
  money. There is no payment gateway.
- Demo auth is a single-user lockdown (email allowlist + one master password);
  swap for Firebase Auth in production.
- All Google Cloud services chosen for their **always-free tiers**.

## 🤝 Contributing
Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
for setup, the test/eval gates, and the no-secrets rule. To report a
vulnerability, follow [SECURITY.md](SECURITY.md) (please don't open a public
issue).

## 📄 License
Licensed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE).
Apache-2.0 is the license used across the Google ecosystem this project builds
on (Agent Development Kit, Gemini samples, Cloud SDKs), and it includes an
express patent grant.

```
Copyright 2026 GOOPHER contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```
