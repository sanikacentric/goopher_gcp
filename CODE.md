# GOOPHER — Codebase Guide (for Engineering Leadership)

A plain-language tour of how the system is built: what each part does, why it exists,
and the key engineering decisions. Audience: technical leaders who want the **big
picture and the rationale**, not a line-by-line read.

**Contents**
1. What GOOPHER is, in one minute
2. The big idea: "LLM orchestrates, code transacts"
3. Repository layout
4. The lifecycle of one request
5. The agents (the brains)
6. The foundations (harness + skills)
7. The tools (the hands)
8. Data, config & API
9. Observability & resilience
10. The user interfaces
11. Scale & load testing
12. Testing, CI/CD & deployment
13. The engineering decisions that matter

---

## 1 · What GOOPHER is, in one minute
GOOPHER is a **unified conversational retail agent**: a customer can ask about products,
check orders, and place orders — by **text, voice, phone, camera, or an uploaded file**,
in **any language**. It is built as a **multi-agent system** on **Google Cloud** (Gemini on
Vertex AI, Cloud Run, Firestore). The customer-facing surface is a **Chrome side-panel
extension**; the brains run as a **FastAPI service** on Cloud Run.

Two pieces:
- **Backend** (`backend/app/…`) — the agents, tools, API, and data layer (Python/FastAPI).
- **Frontend** — a **storefront** website (`site/`) and the **Chrome extension** (`extension/`),
  both plain HTML/CSS/JavaScript (no framework, so they load instantly).

## 2 · The big idea: "LLM orchestrates, code transacts"
The single most important design rule:
> The language model **understands and converses**; **deterministic Python code performs the
> transaction** (placing orders, taking payment).

Why: an AI that can charge a card or change inventory is a safety and audit risk. So GOOPHER
routes every purchase through a **deterministic checkout gate** with **confirm-before-charge**
and **no substitution**. The LLM proposes; code commits. This also makes the system **cheaper
and faster at scale**, because the high-volume "hot path" (routing, status lookups, checkout)
needs **no LLM call** — only open-ended reasoning does.

## 3 · Repository layout
```
backend/app/
  agents/        the brains — one file per agent (see §5)
    harness/     common runtime every agent uses (§6)
    skills/      the capability catalog agents pick from (§6)
  tools/         the hands — catalog/order/checkout/email/fulfillment (§7)
  db/            the data layer (SQLite local / Firestore cloud)
  observability/ live dev portal + Cloud Trace + metrics (§9)
  models/        request/response data shapes (Pydantic)
  config.py      all settings (one place)
  main.py        the API (FastAPI) — every endpoint + the storefront mount
  middleware.py  abuse protection (rate + size limits)
site/            the storefront website (HTML/CSS/JS + product photos)
extension/       the Chrome side-panel app (HTML/CSS/JS)
scale/           load generator for the high-volume demo (§11)
tests/           ~152 automated tests
.github/ + cloudbuild.yaml + Dockerfile   CI/CD + container build
```

## 4 · The lifecycle of one request
What happens when a customer sends "do you have oreos?" (trace this in the live `/dev` portal):

1. **`main.py`** receives the call, checks the **JWT** and **rate/size limits** (`middleware.py`).
2. **Deterministic pre-processing** (no LLM): figure out the **modality** (text/voice/image),
   the **language**, the **channel** (web/phone), and **load this user's memory** from Firestore.
3. **Is it a purchase?** If yes → the **deterministic checkout gate** handles it (cart → payment →
   order), and the LLM is skipped entirely.
4. Otherwise → the **Agent Harness** runs the **orchestrator** (an LLM agent on Gemini), which
   **delegates to one specialist worker**, which **picks a skill** and **calls a tool** that reads
   the **mock retail DB** in Firestore.
5. The reply is **formatted for the channel**, the **memory is saved**, and **every step is traced**
   to the live `/dev` portal and Cloud Trace.

The point: most of that pipeline is **plain Python**; the LLM is one step in the middle, used only
when reasoning is needed.

## 5 · The agents (the brains) — `backend/app/agents/`
GOOPHER uses **four different patterns on purpose** — not everything is an "AI agent":

| Pattern | Used by | Plain meaning |
|---|---|---|
| LLM agent with **native tool-calling** | the orchestrator + 4 workers | the AI decides which tool to call (reliable, production path) |
| LLM agent with **explicit ReAct** | the Advisor only | the AI *shows its plan* — "watch it think" |
| **LLM-as-judge** (not an agent) | the Critic (self-improvement) | one AI call grades a bad answer and writes a lesson |
| **Plain Python** (no AI) | pre-processors, the Guardian | speed/safety — no intelligence needed |

**`orchestrator.py` — the manager (the most important file).**
A real Google ADK **LLM agent** (`goopher_orchestrator`) on **Gemini 2.5 Flash via Vertex AI**.
It understands the request and **delegates to one of four specialist workers** —
`inventory_agent`, `order_agent`, `checkout_agent`, `order_management_agent` — wired as
**"agent-as-tool"** (so the agents can't form loops). It also contains the **deterministic
checkout gate** (purchases never touch the LLM) and the **multilingual** logic (translate a
non-English order to English for the gate, then localize the reply/email back). If the model is
unavailable, it **falls back** to grounded answers from the tools.

**`advisor_agent.py` — the personal shopper.**
The one agent that **explicitly reasons in the open** (Google ADK's `PlanReActPlanner`):
plan → look things up → reason → recommend. It is **read-only** — it can recommend but, by code
assertion, can **never** be given a checkout tool. Used for "recommend something based on my last order."

**`critic_agent.py` — self-improvement (RSI).**
When a customer marks an answer unhelpful (👎), this sends the failed conversation to Gemini acting
as a **judge**, which returns a short corrective **lesson**. High-confidence lessons are stored, and
the next similar question **retrieves and applies the lesson** — **no retraining, no redeploy.** It is
deliberately **not** an ADK agent — just a focused, single-purpose class.

**`guardian.py` — self-healing infrastructure.**
A **synthetic monitor** (no LLM) that runs **probe** transactions and never touches live customer
flows. In the `/dev` portal you can **break a dependency** (Vertex, catalog, fulfillment) and watch it
**DETECT → DIAGNOSE → REMEDIATE → VERIFY** with a circuit breaker. This is the "it heals itself" story.

**`vision_agent.py` — "see it, shop it."**
Sends a camera image + question to **Gemini (multimodal) on Vertex**, recognizes the item, prices it,
and routes an order through the **same checkout gate** (confirm-before-charge).

**The deterministic pre-processors (plain Python, no AI):**
- **`modality_agent.py`** — detects text/voice/image and extracts order IDs.
- **`language_agent.py`** — detects the language (e.g. "¿/¡" ⇒ Spanish) and forces the reply language.
- **`channel_agent.py`** — formats for web vs phone (voice-safe text).

## 6 · The foundations (the platform layer)
GOOPHER isn't a pile of agents — it's a small **platform**, so adding a new agent is fast and safe.

**`agents/harness/agent_harness.py` — one runtime for every agent.**
Every agent (orchestrator, workers, advisor) runs through the **same** wrapper:
build → start a session → run-loop → collect (text/tool-calls/observations) → resilience
(retry/degrade-once) → a clean result object. One tested run-loop instead of copy-pasted code.

**`agents/skills/agent_skill_registry.py` — the capability catalog.**
A **skill** = an instruction + a set of tools, registered **once**. An agent **picks a skill by name**.
Each skill carries a **`read_only` flag enforced in code** (and exposed at `GET /skills`), which is how
we *prove* the Advisor can never transact. The individual skills live in
`skills/{inventory,order,checkout,order_mgmt}_skill.py`.

## 7 · The tools (the hands) — `backend/app/tools/`
Tools are **plain Python** — they do the real work against the data. **None of them call the LLM.**

| File | What it does |
|---|---|
| **`checkout_tool.py`** | The cashier: cart → simulate payment → persist the order (`ORDER_PLACED`). Single and bulk orders. Triggers the confirmation email. **This is the deterministic transaction.** |
| **`order_mgmt_tool.py`** | The **9-stage fulfillment pipeline** (validation → ORDER_PLACED → confirmation → warehouse → shipping → tracking → delivery → invoice), streamed live to `/dev`. |
| **`email_tool.py`** | Order-confirmation email — best-effort (wrapped in try/except so a mail outage can never fail an order). Sends via **Resend** (free tier) or SMTP; localizes to the customer's language. |
| **`inventory_tool.py`** | Catalog search + live stock (`search_inventory`, `check_stock`). |
| **`order_tool.py`** | Order status, history, and **bulk** status (`bulk_order_status` for high-volume order management). |

## 8 · Data, config & API
- **`db/database.py`** — a **repository** abstraction: **SQLite locally** (zero-setup dev) and
  **Firestore in the cloud** (serverless, durable, shared across instances). Holds the catalog,
  orders, `ORDER_PLACED`, and session memory. `search_products` does keyword scoring + department
  detection. *Why Firestore:* with serverless scale-to-zero, in-memory state would be lost — a shared
  DB lets any instance serve any user.
- **`models/schemas.py`** — Pydantic models that validate every request/response (the data "contracts").
- **`config.py`** — **one place** for all settings (model name, Vertex on/off, DB backend, email,
  rate limits, the scale-demo flag).
- **`main.py`** — the FastAPI app and **every endpoint**: `/chat`, `/vision`, `/advise`, `/critic/*`,
  `/orders/bulk`, `/catalog`, `/skills`, the `/dev` portal, `/sim/*` (scale demo), `/version`, `/healthz`.
  It also serves the storefront website.
- **`middleware.py`** — **abuse protection**: per-client **rate limits** (sliding window) and request
  **size limits**, so the service can't be cost-attacked. (The read-only `/sim/*` scale endpoints are
  exempt so a load test isn't blocked by it.)

## 9 · Observability & resilience — `backend/app/observability/`
- **`flow_recorder.py`** — records each turn's steps and powers the **live `/dev` portal**, where you
  can watch the whole pipeline (auth → pre-process → orchestrator → worker → skill → tool → memory) in
  real time. This is the "radical transparency" / "not a black box" story.
- **`telemetry.py`** — structured logging, **Cloud Trace** spans, and metrics. Lets you debug in
  production and see a red span on the exact failing node.
- **Resilience** is built in: the deterministic fallback engine, the Guardian's self-healing, and
  "degrade, don't fail" everywhere.

## 10 · The user interfaces
**Storefront — `site/`** (a normal shopping website):
- `index.html` + `store.css` (pure CSS, gradients, responsive) + `store.js` (vanilla JavaScript that
  fetches `/catalog` and renders product cards). Product images are **real, self-hosted photos** in
  `site/img/`. No framework → instant load.

**Chrome extension — `extension/`** (the conversational assistant):
- `sidepanel.html/.css/.js` — the side-panel UI (login, chat, staged checkout with confirm-before-charge,
  the RSI "teach" button, the Advisor panel). `sidepanel.css` is a dark theme in Google brand colors.
- `api.js` — the calls to the backend. `mic.js` — voice (Web Speech API for speech-to-text + text-to-speech).
  `camera.js` — the camera (getUserMedia). `manifest.json`/`background.js` — Chrome MV3 wiring.
- **Plain JS + CSS, no React** → zero build step, tiny bundle, fast load (ideal for a side panel).

## 11 · Scale & load testing — `scale/`
- **`scale/loadtest.py`** — a load generator that ramps concurrent users and prints throughput,
  latency, and success rate. It has a **HYBRID mode** (`--mix`) that sends realistic production traffic
  in **one run**: ~90% cheap **deterministic** requests + ~10% real **LLM** requests, reporting each
  slice separately. (Details and talking points: `SCALE.md`, `SCALE-LEADERSHIP.md`, `SCALE-CHEATSHEET.md`.)
- **`/sim/chat` + `/sim/stats`** (in `main.py`) — read-only, **no-LLM, no-write** endpoints that let the
  load test push real volume **without burning LLM quota or mutating data**, so the test measures **the
  app's autoscaling** (a Cloud Run property), not the model.

## 12 · Testing, CI/CD & deployment
- **`tests/`** — ~**152 automated tests** plus evals, gating every change. A **CI-sim** blocks the
  Google packages and runs everything through the deterministic fallback, which **proves the production
  fallback path is safe** even though the live ADK path can't run in CI.
- **CI/CD** — push to `main` → **GitHub Actions → Cloud Build → Cloud Run**. Secrets (JWT, master
  password, Resend key) are injected at deploy time from GitHub secrets, **never committed**. The Cloud
  Run scale settings (instances/concurrency) are baked into the deploy so they persist.
- **`Dockerfile`** — containerizes the app (backend + the storefront `site/`).
- **`/version`** — a build marker so you can confirm exactly which code is live.

## 13 · The engineering decisions that matter (and why)
| Decision | Why |
|---|---|
| **LLM orchestrates, code transacts** | Safety + audit: the AI can never charge a card or substitute an item. |
| **Agent-as-tool (not transfer-back)** | Loops are impossible *by construction*, not by prompting. |
| **Don't make everything an agent** | Match the pattern to the job: deterministic for routing/checkout, ReAct only for the read-only advisor, LLM-as-judge for self-improvement → speed, cost, reliability. |
| **Stateless app + Firestore session state** | Cloud Run can scale horizontally / to zero; any instance serves any user. |
| **One harness + a skill registry** | Platform thinking — adding an agent is fast, and the `read_only` guardrail is enforced in code. |
| **Best-effort side-effects (email)** | A notification outage must never fail a paid order. |
| **Isolate new agents (Vision/Advisor/Guardian/Critic)** | Ship innovation without risking the working flows. |
| **Deterministic hot path** | The expensive LLM is used only when reasoning is needed → cheaper, faster, and easy to scale. |

---

### One-paragraph summary for a leadership readout
*GOOPHER is a multi-agent retail assistant on Google Cloud, organized as a small platform: a single
orchestrator (Gemini on Vertex) delegates to specialist agents that pick named skills and call plain-Python
tools against Firestore, with every agent running through one shared, observable runtime. The defining rule
is "LLM orchestrates, code transacts" — purchases go through a deterministic, auditable gate, so the AI
never moves money, and the high-volume hot path needs no model call. That same design is what lets it scale
cheaply on Cloud Run, learn from feedback (the self-improving Critic), and heal itself (the Guardian) — all
visible live in a developer portal. The codebase is deliberately conventional and well-tested (~152 tests,
CI/CD), so it reads like a production system, not a prototype.*
