# GOOPHER — Architecture

> Unified conversational retail agent for **JCPenney "Casual Dresses for Women"**,
> delivered as a Chrome extension backed by a Google ADK multi-agent service on
> Google Cloud (free tier).

---

## 1. System overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CHROME EXTENSION "GOOPHER"  (Manifest V3, side panel)                          │
│  ─ Login (JWT)   ─ Chat UI   ─ Channel/Language toggles   ─ Image/File upload   │
└───────────────┬────────────────────────────────────────────────────────────────┘
                │  HTTPS (Bearer JWT)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  FastAPI SERVICE  (Cloud Run)                                                  │
│  Middleware: rate limiting + request-size limits (DoS guard)                    │
│  Auth: single-user lockdown — email allowlist + master password (fail-closed)  │
│  /auth/login  /auth/me  /chat  /orders/bulk  /catalog  /healthz  /metrics  /dev │
│                                                                                │
│   ┌────────────────────────────────────────────────────────────────────────┐ │
│   │  goopher_orchestrator — MAIN unified agent (root LlmAgent, Gemini) [T2]   │ │
│   │  In charge of the turn; coordinates ALL sub-agents below it, then         │ │
│   │  composes the customer-facing reply. (Deterministic backup if ADK off.)  │ │
│   │                                                                          │ │
│   │   ├─ context_pipeline (SequentialAgent — ALWAYS runs, in order):         │ │
│   │   │     memory_agent [T3] → modality_agent [2A-6] → language_agent [2A-5]│ │
│   │   ├─ inventory_agent ──owns──► search_inventory / check_stock /          │ │
│   │   │                            get_product_details              [2A-1]   │ │
│   │   ├─ order_agent     ──owns──► get_order_status /                        │ │
│   │   │                            list_customer_orders / bulk_status [2A-2,R3]│ │
│   │   └─ channel_agent   ──owns──► select_channel (web / phone)     [2A-4]   │ │
│   │                                                                          │ │
│   │  Observability: Cloud Trace + structured logs + /metrics [T10]          │ │
│   │  Dev portal /dev — live end-to-end flow visualizer (SSE)                │ │
│   └───────────────┬──────────────────────────────────────────────────────────┘ │
│                   │ sub-agents call ADK function tools (in-process) [T5]        │
└───────────────────┼──────────────────────────────────────────────────────────┘
                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  DATA LAYER  (Repository abstraction)                                          │
│   SQLite (local/dev/CI)  ◀──same code──▶  Firestore (GCP free tier) [T7]         │
│   Collections: products · orders · customers · sessions (conversation memory)  │
│   Seeded from backend/data/goopher_catalog.json  (mock clothing + food data)  │
└──────────────────────────────────────────────────────────────────────────────┘

LLM: Gemini 2.5-flash on Vertex AI ($300 credit) [T6] · OpenAI gpt-4o-mini (toggle)
CI/CD: push to main → GitHub Actions → test+eval → Cloud Build → Cloud Run [T17]
```

---

## 2. Request flow (one chat turn)

```
User types/【uploads】 in the side panel
   │
   ▼
POST /chat  { message, session_id, channel, language, voice, attachments } + JWT
   │
   ▼ rate-limit + size-limit middleware  ─► 429 / 413 if abused
   ▼ auth.decode_token (allowlist+master pw) ─► 401 if invalid     [T1]
   │
   ▼ AgentService.run_turn()  (opens a trace span)                 [T10]
   │
   ▼ ADK path — goopher_orchestrator (MAIN agent) coordinates its sub-agents:
        invoke_agent goopher_orchestrator                 (root, in charge)
          ├─ invoke_agent context_pipeline   (always, in order):
          │     memory_agent [T3] → modality_agent [2A-6] → language_agent [2A-5]
          ├─ invoke_agent inventory_agent  (or order_agent)   ← worker picked
          │     └─ execute_tool search_inventory              ← worker owns tool
          ├─ invoke_agent channel_agent → select_channel      [2A-4]
          └─ generate_content gemini-2.5-flash   (compose grounded reply)
   ▼ Backup path (no LLM): deterministic modality/language/channel + intent
        router → tools → template/LLM phrasing  (separate, never mixed)
   ▼ user + assistant turns persisted to session memory (Firestore in cloud) [T3]
   ▼ ChatResponse { reply, language, channel, used_tools, trace_id }
```

The **session_id** is the spine that preserves context (Requirement T3 + the
global "maintain context when switching" rule). Because language/channel/
modality are all read from and written to the same `SessionMemory`, a shopper
can start on web in English, continue on phone in Spanish, and the agent keeps
the thread.

### 2a. Session memory — the `MEMORY · session updated` step (T3)

The **last stage of every chat turn** is `MEMORY · session updated`: the agent
**saves the conversation to memory**. After GOOPHER answers, it writes **both
sides of the exchange** — the user's question *and* the assistant's reply — into
**session memory**, keyed by the turn's `session_id` (e.g. `sess-nst14x8icr…`,
shown in the `/dev` header).

> dev-portal card: `MEMORY · session updated · persisted user + assistant turns
> to session memory`

**Why it matters — conversational continuity.** Because each turn is persisted,
context carries across turns:
- "what's the price of the tiered midi dress?" → "is it in **navy**?" → "**order
  it**" — the agent knows what *"it"* refers to.
- It also remembers the **language and channel**, so a shopper can start on Web in
  English and continue on Phone in Spanish and keep the thread.

**Where the memory lives:**
- **Cloud:** **Firestore** — durable and shared across Cloud Run instances, so
  context survives even if the next request lands on a different container or
  after scale-to-zero. (The earlier `SESSION · memory.get` step shows
  `backend=firestore`.)
- **Local:** an in-process store.

So the full pipeline reads end-to-end as:
```
AUTH → SESSION (memory.get: load prior context)
     → PRE-PROCESS (modality · language · channel)
     → ORCHESTRATOR → inventory_agent (answer)
     → MEMORY (session updated: save this turn)   ← persists the exchange
```
*Every turn loads prior context at the start and persists the new turn at the
end (to Firestore in the cloud), so the agent has real, durable memory and stays
coherent across turns, channels, and languages.*

---

## 3. Components & requirement mapping

| Component | File(s) | Requirement |
|-----------|---------|-------------|
| Chrome extension "GOOPHER" | `extension/` (MV3, side panel) | **2A** |
| Customer authentication | `backend/app/auth/auth.py`, `/auth/*` | **T1** |
| ADK orchestrator | `backend/app/agents/orchestrator.py` | **T2** |
| Memory agent (context) | `backend/app/memory/memory_agent.py` | **T3**, global |
| Agent skills + **registry** | `backend/app/agents/skills/*`, `agent_skill_registry.py`, `GET /skills` | **T4** |
| In-process function tools (inventory/order) | `backend/app/tools/*` | **T5**, 2A-1, 2A-2 |
| Gemini LLM (free tier) | `config.gemini_model`, orchestrator | **T6** |
| Google Cloud stack (free tier) | Firestore + Cloud Run + Cloud Trace | **T7**, T14 |
| Channel subagent (phone/web) | `backend/app/agents/channel_agent.py` | **2A-4** |
| Language subagent | `backend/app/agents/language_agent.py` | **2A-5** |
| Modality subagent | `backend/app/agents/modality_agent.py` | **2A-6** |
| Vision subagent (camera, Gemini Vision) | `backend/app/agents/vision_agent.py`, `/vision` | **2A-6** |
| Checkout (single + bulk, transactional gate) | `backend/app/tools/checkout_tool.py`, `_try_checkout` | **4** |
| Order management (9-stage fulfillment) | `backend/app/tools/order_mgmt_tool.py` | **5** |
| Cart / orders panel | `extension/`, `/orders/mine` | **2A** |
| Phone channel = mobile-device simulator | `extension/sidepanel.*` | **2A-4** |
| Bulk order from an uploaded file | `orchestrator._try_file_bulk_order` | **3** |
| Contextual ordering ("order it") | `orchestrator`, `inventory_tool.get_last_viewed` | **4** |
| Individual + high-volume orders | `order_tool.bulk_order_status`, `/orders/bulk` | **3** |
| Self-service GenAI front end | extension + `/chat` | **4** |
| **Self-healing Guardian** (circuit breaker, failover, chaos) | `backend/app/agents/guardian.py`, `/dev` | **T10** |
| Developer portal (live flow visualizer) | `backend/app/static/dev_portal.html`, `/dev` | **T10** |
| Single-user lockdown (allowlist + master pw, fail-closed) | `backend/app/auth/auth.py`, `config` | **T1 / Sec** |
| Abuse protection (rate limit + size limit, DoS) | `backend/app/middleware.py` | **Sec** |
| Evals | `evals/` | **T8** |
| Unit tests | `tests/` | **T9** |
| Observability | `backend/app/observability/telemetry.py` | **T10** |
| README | `README.md` | **T11** |
| Architecture writeup | this file | **T12** |
| Production-grade, Cloud-deployable | Dockerfile + Cloud Run | **T14** |
| Comments explaining logic | throughout | **T15** |
| Dockerized | `Dockerfile`, `docker-compose.yml` | **T16** |
| CI/CD via GitHub Actions | `.github/workflows/deploy.yml` | **T17** |

---

## 4. Why these choices (free-tier first)

- **Gemini `gemini-2.5-flash`** — fast, natively multimodal (covers image/voice
  for the modality subagent), and available on the AI Studio free tier (T6).
- **Firestore** — the only Google Cloud database with a genuine *always-free*
  tier (1 GiB, 50K reads/day). The `Repository` abstraction lets the identical
  agent/tool code run on SQLite locally and Firestore in the cloud (T7).
- **Cloud Run** — scale-to-zero, 2M free requests/month, perfect for a
  bursty chat backend; `min-instances=0` keeps cost at $0 when idle (T14).
- **Cloud Trace** — 2.5M free spans/month for the built-in observability (T10).
- **MCP** — decouples tools from the agent so the same inventory/order tools
  are reusable by any MCP client (e.g. Claude Desktop), not just GOOPHER (T5).

---

## 4a. LLM models used

| Model | Provider | Where | Used for |
|---|---|---|---|
| **`gemini-2.5-flash`** | Google (Gemini) | **Vertex AI** (cloud) · AI Studio (local) | the **primary model** |
| **`gpt-4o-mini`** | OpenAI | local only | swappable alternate + vision fallback |

- **Production is single-model: `gemini-2.5-flash` on Vertex AI.** The cloud runs
  `LLM_PROVIDER=gemini`, `USE_VERTEXAI=true`, authenticated by the Cloud Run
  service account, **with no OpenAI key** — so OpenAI is never invoked in prod.
- That one Gemini model powers **all four** intelligent paths: (1) the ADK
  orchestrator + worker sub-agents and grounded reply phrasing, (2) multilingual
  localization, (3) **camera Vision** (it's natively multimodal — same model,
  via the `google.genai` SDK with `thinking_budget=0`; see §5c), and (4) the
  **explicit-ReAct Shopping Advisor** (`PlanReActPlanner`, read-only; see §5f).
- **Two agent styles, one model:** native **function-calling `LlmAgent`s** for
  the production/transactional paths, and an **explicit ReAct** agent
  (`PlanReActPlanner`) for open-ended advice — see §5f.
- `gpt-4o-mini` is the `LLM_PROVIDER=openai` alternate used locally and as a
  vision fallback; wired but inactive in the cloud.
- **No LLM is used** for: the deterministic intent router, the
  language/channel/modality pre-processing, the transactional checkout gate, or
  the Guardian self-healing — the model understands and phrases, deterministic
  code executes (the "LLM orchestrates, code transacts" guardrail, §5b).

---

## 5. Resilience / graceful degradation

The orchestrator has **two execution paths** behind one interface:

1. **ADK + Gemini** — the production path (real LLM reasoning + tool calling).
2. **Deterministic fallback** — intent routing over the same in-process tools,
   used automatically when the API key or ADK package is absent, or if an ADK
   turn errors.

This is why unit tests and evals run offline in CI in seconds, and why a
transient LLM outage degrades to still-useful, grounded answers instead of a
hard failure.

---

## 5a. Why only inventory/order are ADK agents (design rationale)

A deliberate, hard-won decision: **only the two capabilities that genuinely
reason are ADK `LlmAgent`s** (`inventory_agent`, `order_agent`). The
modality / language / channel / memory steps are **deterministic Python**, run
as a pre-processing phase before the orchestrator — *not* ADK sub-agents.

**Why not make everything an agent?** We tried (see `LEARNINGS.md §10`). Forcing
the deterministic steps into `LlmAgent`s repeatedly failed:
- `SequentialAgent` cannot be wrapped as an `AgentTool` (breaks the single-
  response contract → red span in Cloud Trace → fell back to backup).
- Tool-only agents emit no final text → `RuntimeError: ADK produced no text
  response`.
- Per-turn context (session id) didn't propagate reliably through ADK's tool
  execution context.
- Each added a Gemini call (~5/turn): more cost, latency, and quota burn — for
  **zero functional benefit**, since detecting a language or modality needs no
  intelligence.

**The principle:** *LLM agents for reasoning/decisions; plain functions for
deterministic transforms.* This keeps the genuine multi-agent value — the
orchestrator selecting a worker that owns its tools — while making the pipeline
reliable, fast, and cheap.

```
goopher_orchestrator   ◄── MAIN agent (ROOT LlmAgent, decides + delegates)
  │  delegates to →
  ├─ inventory_agent   (ADK worker → search_inventory / check_stock / details)
  └─ order_agent       (ADK worker → order_status / list_customer_orders / bulk)

  preceded by deterministic PRE-PROCESS (Python, no LLM):
     modality · language · channel · memory     (100% reliable, free, instant)
```

The dev portal labels the deterministic steps "PRE-PROCESS" and the orchestrator
"ORCHESTRATOR (gold)" so the two layers are never confused.

**Cloud Trace note:** the deterministic steps are *not* ADK agents, so they don't
produce ADK/`GenAI` spans. They ARE wrapped in lightweight OpenTelemetry child
spans (`preprocess.modality_agent`, `preprocess.language_agent`,
`preprocess.channel_agent`, `preprocess.adapt_for_phone`, `session.memory_get`,
`memory.session_update`) so they still appear under `chat_turn` in Cloud Trace —
fast, no-LLM, alongside the genuine ADK + Gemini spans. So Cloud Trace shows the
full picture: deterministic glue *and* the real agent reasoning.

---

## 5b. Why checkout is deterministic — the transactional gate

**Principle: the LLM orchestrates and converses; it does not execute
money-affecting actions. A purchase is transactional — it must be grounded,
structured, reproducible, and auditable, never improvised by a model.**

Checkout therefore runs through a single shared handler,
`AgentService._try_checkout()`, called in `run_turn()` **before** the ADK/LLM
branch. If the message is a transaction ("place an order", "buy …", bulk), it is
handled by deterministic code and the LLM never touches it. Everything else
(browsing, stock questions, order status, chit-chat) flows to the ADK agents as
normal.

```
run_turn()
   │  (after deterministic PRE-PROCESS: auth · session · channel/lang/modality)
   ▼
   _try_checkout(text, customer_id)   ◄── THE GATE (deterministic, structured)
   │
   ├─ transaction?  YES ─► resolve product (by name or SKU; REFUSE, never
   │                        substitute) → place_order() → simulated payment →
   │                        run_fulfillment() → REAL ORDER_PLACED DB write →
   │                        build {checkout payload} + deterministic receipt
   │                        🛒 cart → 💳 processing → ✅ paid → 🎉 ORDER PLACED
   │
   └─ transaction?  NO  ─► ADK path (_generate_adk: orchestrator → worker
                            sub-agents) OR deterministic fallback
```

**Why this is the correct approach (the guardrail / "LLM ≠ cashier" pattern):**

| Property | If the LLM did checkout | With the deterministic gate |
|---|---|---|
| Determinism | price / total / order-id can vary or be mis-phrased | same input → same output, always |
| No hallucination | model may invent or drop details | totals, order id, tracking are computed, not generated |
| Safety on irreversible acts | model implicitly charges / picks a substitute | charging & item selection are explicit, rule-bound code |
| No silent substitution | "oreo not found → here's a cheez-it" | unresolved item is **refused**, never swapped |
| Auditability / compliance | hard to prove what was charged | real `ORDER_PLACED` row + full trace in `/dev` |
| Testability | LLM wording can't be asserted reliably | unit-tested transaction path (no LLM needed) |
| Latency & cost | extra LLM round-trip per purchase | checkout skips the LLM entirely |
| Behavioral parity | cloud (ADK on) ≠ local (ADK off) | identical behavior in every environment |

This separation also fixed a real production bug: with the ADK path on in the
cloud, checkout used to go through the LLM agent, which phrased its own reply and
never produced the structured cart/`ORDER_PLACED` payload — so the cart silently
vanished. Routing checkout through the gate makes every path produce the same
grounded, structured result.

**Trade-off & upgrade path (so the design scales):** the gate currently detects
intent via keywords ("place an order", "buy", "checkout"). The clean evolution
keeps the architecture intact — replace the keyword gate with an **LLM
intent-classifier that only extracts `(intent, product, quantity)` as
constrained JSON**, while **execution stays in the deterministic handler**. This
is the same idea as constrained tool/function calling: the model proposes
parameters; deterministic, validated code performs the transaction. The LLM
never decides, on its own, to charge a card.

---

## 5c. The Vision subagent — camera "see it, shop it" (Gemini Vision)

A dedicated, self-contained subagent (`vision_agent.py`) that is **separate from
the existing `modality_agent.py` pipeline** (left untouched). It powers the
`POST /vision` endpoint, which the extension calls from a camera popup window.

```
camera popup (extension)
   capture frame + spoken/typed question
   ▼  POST /vision { image_b64, question }
vision_agent.handle_vision()
   1) RECOGNIZE  — Gemini Vision via the unified google.genai SDK on VERTEX AI
                   (service-account auth; no API key). thinking_budget=0 +
                   max_output_tokens=2048 so 2.5-flash "thinking" can't starve
                   the answer. OpenAI vision is a local fallback.
   2) RESOLVE    — map the recognized name to a real catalog product
                   (resolve_variant_by_name); if we don't carry it → say so,
                   never substitute.
   3) ACT        — order intent → delegate to the SAME transactional gate
                   (_try_checkout) in PREVIEW mode → cart + "please confirm";
                   else → answer the price + availability.
```

**Confirm-before-charge (parity with text & voice).** Camera orders now PREVIEW
(`_try_checkout(..., confirm=False)` → cart + "🟡 please confirm") rather than
charging on capture. The pending payload carries `confirm_text` (the resolved
SKU order); the extension's Confirm button (or a spoken/typed "confirm order")
re-sends THAT to `/chat` with `confirm=True`, so exactly the recognized item is
placed — never a substitute. Verified end-to-end in `tests/test_vision_agent.py`
(vision preview → confirm → placed).

Design notes that proved important (see `LEARNINGS.md §3.16`):
- **Vertex, not AI Studio.** The cloud runs `USE_VERTEXAI=true` with *no* API
  key, and the legacy `google.generativeai` SDK cannot reach Vertex — recognition
  must use the unified `google.genai` client (`vertexai=True`).
- **Disable thinking.** `gemini-2.5-flash` spends output tokens "thinking" before
  the visible answer; a small token cap returns empty. `thinking_budget=0` +
  2048 tokens fixes it.
- **Recognition recognizes; the gate transacts.** Ordering by camera flows
  through `_try_checkout`, so the cart/receipt/`ORDER_PLACED` are identical to a
  typed order — the LLM never executes the purchase.

Vision turns are recorded to the `/dev` portal as a distinct `vision` flow kind.

---

## 5d. Ordering by file & natural language

- **Bulk order from an uploaded file — text, CSV, or Excel.** `_try_file_bulk_order`
  detects the format from the bytes/filename/mime and parses accordingly:
  - **`.xlsx`** → **openpyxl** (an `.xlsx` is a binary ZIP, so it must be parsed,
    NOT decoded as text — decoding it yielded garbage and silently fell back to a
    default basket). `_parse_tabular` locates the `product_name` / `sku` /
    `order_quantity` columns by header and extracts `(name, sku, qty)` per row.
  - **`.csv`** with headers → the same tabular parser; **plain `.txt`** →
    `_parse_order_file` (tolerant of `order - 15 oreo cookies`, `lego x1`,
    `3x oreos`, `TOY-NRF-3003`, …).
  Each line resolves **by SKU first, then product name** (never substitutes; unknown
  lines are skipped and reported). It then **PREVIEWS the cart and asks "please
  confirm"** — parity with text/voice/camera — and the Confirm button re-sends a
  compact `__bulk_confirm__ SKU=qty; …` marker so the order is placed **without
  re-uploading the file** (recognized in `_resolve_order`). Verified end-to-end on a
  real enterprise PO: 9 items with exact quantities (Cheez-It ×50, Coca-Cola ×120,
  Lay's ×200, …).
- **Natural order phrasing.** `_is_order_intent` recognizes conversational orders
  ("order balls for me", "get me a lego", "i want to buy oreos") while excluding
  status/tracking queries — so they hit the structured gate (and produce a cart)
  instead of falling through to free-form LLM phrasing.

---

## 5e. The Guardian — a self-healing agent (isolated)

A separate, self-contained agent (`guardian.py`) that adds **autonomous fault
recovery** with full visibility, and — critically — **touches none of the live
flows** (`/chat`, `/vision`, checkout are unchanged). It is a *demonstrator and
control plane* for resilience, driven by **synthetic transactions** (the same
idea as production synthetic monitoring), so it can prove recovery without any
risk to real shopping traffic.

```
GET  /dev/health      → component health (the live strip in /dev)
POST /dev/chaos       → inject / clear a fault on a component  (demo control)
POST /dev/heal-demo   → run a synthetic transaction through a component
background tick()     → probe down components → "heal forward" when they recover
```

**Resilience policy** (`Guardian.protect`):
```
run primary()
 ├─ success → component 🟢
 └─ failure →
      DETECT   classify the error; bump the circuit-breaker counter
      DIAGNOSE map to the playbook (root cause)
      REMEDIATE optional self-repair (e.g. re-seed) → retry with backoff →
               fail over to a fallback so the CUSTOMER is never errored
      VERIFY   mark healthy (recovered on primary) or healing (serving via
               failover); stream the whole thing to /dev as a `heal` record
   + circuit breaker: after N failures the circuit OPENS (skip the known-bad
     primary, serve the fallback); a background probe HEALS FORWARD and closes
     the circuit once the fault clears.
```

**The 4 steps, as they stream to the `/dev` HEAL card:**
1. **🔎 DETECT** — `1. DETECT — vertex.synthetic_request failed: ChaosError…`
2. **🧠 DIAGNOSE** — `2. DIAGNOSE — LLM provider unavailable (Vertex 5xx / empty / timeout)`
3. **🔧 REMEDIATE** — `retry #1 failed → retry #2 failed → failover (customer unaffected)`
4. **✅ VERIFY** — `4. VERIFY — serving via failover; probing to heal forward`
…and on recovery: `PROBE → HEAL FORWARD (primary is back → closed the circuit)`.

The whole flow at a glance:
```
        ┌──────────────── circuit breaker ────────────────┐
run op ─┤  ✅ success → 🟢 healthy                          │
        │  ❌ failure → DETECT → DIAGNOSE → REMEDIATE       │
        │               (self-repair → retry → failover)   │
        │               → VERIFY (🟢 healthy / 🟠 healing)  │
        └──────────────────────────────────────────────────┘
                 ▲                                   │
                 └── HEAL FORWARD ◀── background probe┘
                     (fault cleared → restore primary, close circuit)
```

**Patterns:** circuit breaker · retry-with-jittered-backoff · failover / graceful
degrade · self-repair · health-probe-driven recovery · chaos injection (an
on-demand, deterministic fault injector — like Chaos Monkey — so the demo is
repeatable). The `/dev` portal renders a **health strip** (🧠 Vertex · 🗄️ Catalog
· 📦 Fulfillment) plus chaos buttons; recoveries appear as purple `heal` records.

**Demo control (where the buttons are):** open `/dev` → the **🛡️ Guardian** panel
(pinned under the legend) → **💥 Kill Vertex** (the Vertex LED goes 🟠) → **▶
Vertex** (a synthetic request streams the HEAL card) → **✅ Restore all** (heals
forward to 🟢).

**Why isolated (design choice):** the existing flows were already working and
demo-critical, so Guardian was built to *never* be able to break them — it wraps
its own synthetic units of work, not the production calls. The same `protect()`
API could later wrap real operations behind a flag, with zero change to the
engine. See `LEARNINGS.md §3.19`.

---

## 5f. The Shopping Advisor — explicit ReAct (`PlanReActPlanner`), isolated

GOOPHER deliberately runs **two agent styles on the same Gemini 2.5 Flash**, and
picks the right one per job:

| Style | Where | Why |
|---|---|---|
| **Native function-calling `LlmAgent`** | the 4 production workers + orchestrator (`orchestrator.py`) | Fast, reliable, no brittle text parsing. ReAct *paradigm* via Gemini's structured tool-calling. Used for search, orders, and the **transactional** checkout path. |
| **Explicit ReAct (`PlanReActPlanner`)** | the **Shopping Advisor** (`advisor_agent.py`, `POST /advise`) | A read-only concierge that **visibly** PLANS → ACTS over tools → REASONS → ANSWERS. Surfaces the reasoning trace as a demo artifact. |

**Why the advisor is the *right* place for explicit ReAct** — it's the only use
case that is both **read-only** (it recommends, never places an order — no money
moves) and **genuinely multi-hop** (*"a healthy snack under $4 that pairs with my
last order"* needs order-history lookup → inventory search → price filter →
compare → recommend). Everywhere else, ReAct would only add latency, tokens, and
parsing fragility:
- **checkout / fulfillment** are deliberately deterministic (the transactional
  gate, §5b) — we never want the LLM *planning and executing* a payment;
- **order status** is single-hop — nothing to plan;
- the **orchestrator** just routes — a planner would slow *every* turn (incl.
  voice). If we ever want model-side planning there, the right tool is ADK's
  **`BuiltInPlanner`** (native Gemini thinking), **not** `PlanReActPlanner`.

**Isolation guarantee** (same discipline as Vision/Guardian): a brand-new module
with its **own `InMemoryRunner`** (`app_name="goopher-advisor"`), reached by its
**own `POST /advise`** endpoint, given **READ-ONLY tools only** (inventory
search/details + order lookup — the tool set is asserted **disjoint** from the
checkout skill in `tests/test_advisor_agent.py`). It never touches `/chat`,
`/vision`, the memory store, or any checkout code.

```python
# advisor_agent.py (essence)
from google.adk.agents import LlmAgent
from google.adk.planners import PlanReActPlanner

advisor = LlmAgent(
    name="shopping_advisor",
    model=settings.gemini_model,             # same Gemini 2.5 Flash
    planner=PlanReActPlanner(),              # <-- explicit ReAct (visible plan)
    instruction=ADVISOR_INSTRUCTION,        # "recommend only — never place an order"
    tools=skills.get_tools(*skills.read_only_skill_names()),  # READ-ONLY skills only
)
```

**Reliability fixes that proved important (this session):**
- **"Plan but no answer" stall.** `gemini-2.5-flash` *thinking* collides with
  `PlanReActPlanner`: the model emits the plan + first tool call, then thinking
  eats the output on the next turn and the visible `/*FINAL_ANSWER*/` never lands
  (the same bug we fixed on Vision). Fix: `thinking_budget=0` +
  `max_output_tokens=4096` on the advisor's generate-config. Safety net: the
  harness captures tool **observations**, and if a final answer is ever still
  missing, a one-shot **grounded synthesis** turns those observations into the
  recommendation — the shopper always gets a real answer, with the plan still
  shown.
- **Context-aware recommendations.** An empty 🧠 tap reads the shopper's MOST
  RECENT order and recommends from the **same department at a similar-or-lower
  price** (e.g. a $17.99 toy → other toys ~≤ $18) — not a hardcoded "snacks under
  $4". Explicit constraints the shopper types still win.

The advisor runs through the **common AgentHarness** (§5h) like every other agent.

---

## 5g. The Agent Skill Registry (T4)

An **agent skill** = a named capability bundling an `INSTRUCTION` (teaches the LLM
when/how to use it) + a set of callable `get_tools()`. The four skills —
`inventory`, `order`, `checkout`, `fulfillment` — are registered ONCE in
`agent_skill_registry.py` (`AGENT_SKILL_REGISTRY`), the single source of truth.

Agents **pick their skills by name** from the registry instead of importing skill
modules directly:

| Agent | Skills it picks | |
|---|---|---|
| `inventory_agent` | `inventory` | `skills.get_skill("inventory")` |
| `order_agent` | `order` | |
| `checkout_agent` | `checkout` (transactional) | |
| `order_management_agent` | `fulfillment` (transactional) | |
| `shopping_advisor` (ReAct) | `inventory` + `order` | `skills.get_tools(*skills.read_only_skill_names())` |

Each `AgentSkill` carries a `read_only` flag. Transactional skills (`checkout`,
`fulfillment`) are `read_only=False`; browse/track skills are `read_only=True`.
The read-only advisor composes **only read-only skills** and asserts it at build
time — so it can never be handed a place-order tool (turning the isolation
guarantee into code; verified in `tests/test_agent_skill_registry.py`).

**Introspection:** `GET /skills` returns the whole registry (name, title,
description, `read_only`, tool names) — a live capability map for the dev portal
and the CTO. Two runtime "picking" levels remain unchanged: the **orchestrator
picks the agent** (AgentTool), and each **agent picks the tool** within its skill
(function-calling). The registry adds an explicit, inspectable **skill** layer
beneath both.

---

## 5h. The Agent Harness (scaffolding) — common runtime for ALL agents

Every ADK agent needs the same runtime "scaffolding" to go from *configured* to
*reliably runnable*:

```
build the agent → create a Runner → ensure the session exists →
stream the turn → collect (text / tool-calls / observations) →
apply resilience (retry, graceful failure) → return a STRUCTURED result
```

That boilerplate used to be copy-pasted inside the orchestrator's `_generate_adk`
**and** the advisor. It now lives ONCE in a dedicated package —
**`backend/app/agents/harness/`** (`AgentHarness` + `AgentRunResult`) — and is the
**common scaffolding shared by all agents**:

| Caller | Harness | Runs |
|---|---|---|
| `AgentService` (production) | `AgentHarness("orchestrator", app="goopher", build_root_agent)` | orchestrator + its 4 worker sub-agents |
| Shopping advisor | `AgentHarness("advisor", app="goopher-advisor", _build_advisor)` | the ReAct advisor |

**`AgentHarness`** (`agent_harness.py`):
- `ready()` — builds the Runner once; **degrades gracefully** (returns `False`,
  never raises) when ADK/Gemini is absent, so the caller uses its fallback (the
  orchestrator drops to the deterministic engine; the advisor returns an
  "enable Gemini" message).
- `run(user_id, session_id, prompt, retries=1)` — ensures the session, streams the
  turn, and returns an **`AgentRunResult`**: `final_text`, `last_text`,
  `transcript` (all text, for ReAct parsing), `used_tools`, `observations`
  (tool results), plus `steps`/`attempts`/`error` for telemetry. `retries>1`
  re-runs a turn on a transient error — used ONLY by the read-only advisor, never
  on a transactional turn.
- google-adk / google-genai are imported **lazily**, so importing the harness
  never requires the heavy packages (CI runs without them).

This is a pure refactor — behavior is identical (same Runner, same event loop,
same "prefer final, fall back to last, raise if empty" semantics). The win is one
tested, observable, resilient scaffold instead of two inline copies. Verified in
`tests/test_agent_harness.py` (ready/unavailable, event collection, retry) with
the rest of the suite unchanged.

The planner emits `/*PLANNING*/ … /*ACTION*/ … /*REASONING*/ … /*FINAL_ANSWER*/`
tags; `_split_react()` splits the **final recommendation** (shown as the reply)
from the **reasoning trace** (shown in the extension's collapsible *"🧠 How
GOOPHER reasoned (ReAct plan)"* panel — the 🧠 button on the composer).

**The CTO talking point:** *"Native function-calling agents for transactions —
reliable, deterministic where money moves — and an explicit ReAct agent for
open-ended advice, with the plan shown live. We chose each deliberately, and kept
ReAct strictly off the transactional path."*

---

## 5i. The fulfillment / order-management pipeline (Req 5)

The 9-stage **FULFILLMENT** pipeline in `/dev` — Order Validation → Inventory
Check → Insert `ORDER_PLACED` → Order Confirmation → Warehouse → Shipping →
Tracking → Delivery → Invoice — is the **order-management agent's** capability:

| Layer | Identity |
|---|---|
| Agent | `order_management_agent` (one of the 4 ADK workers) |
| Skill (registry) | `fulfillment` — *Order Fulfillment Pipeline*, **transactional** |
| Tool | `run_fulfillment` (`order_mgmt_tool.py`) — runs the 9 stages, streams each as a `kind="fulfillment"` record |

**But it executes DETERMINISTICALLY, not as an LLM step.** For a real purchase it
is triggered the moment payment succeeds, from inside the checkout gate:

```
checkout gate → place_order()            (checkout_tool.py)
   → payment succeeds
   → _run_fulfillment_safe(order_id) → run_fulfillment()   ← the 9 stages
```

So the agent *owns* the capability (and the orchestrator could delegate to it on
request, e.g. "re-run fulfillment for ORD-50066"), but money-and-inventory work
**runs as deterministic code** — reliable, auditable, never skipped or
hallucinated. Each stage commits to the SAME `fulfillment` record (deduped by id),
so the portal shows ONE card with 9 stages, not nine cards. This is the
"LLM orchestrates, code transacts" guardrail (§5b) applied end-to-end.

---

## 5j. State & memory model — how all agents maintain state

State is **centralized, durable, and shared by `session_id`** — not scattered
per-agent. There are distinct layers:

| Layer | Where | Holds | Scope |
|---|---|---|---|
| **Session memory** (primary) | `memory/memory_agent.py` — `InMemoryStore` (local) / **`FirestoreStore`** (cloud) | `turns` (history w/ channel·language·modality) + `facts` (working memory) | per `session_id`, **durable & shared across Cloud Run instances** |
| **ADK session** | the `AgentHarness` (`session_service.create_session`) | ADK's internal conversation context | per `session_id`, created once |
| **Working-memory facts** | `_LAST_VIEWED` (`inventory_tool.py`); `memory.remember(...)` | last product viewed; sticky language/channel | enables "order it / the above item" |
| **Per-turn ephemeral** | `AgentService._last_checkout` | current turn's cart/receipt for the UI | one turn only |
| **Guardian state** | `guardian.py` | component health + circuit-breaker state | isolated, no conversation state |
| **Client state** | extension (`chrome.storage.local`) | stable `session_id`, auth token, cart/UI | per browser profile |
| **Business data** | Firestore / SQLite repository | catalog, orders (`ORDER_PLACED`), customers | system of record |

**Lifecycle per turn** (`run_turn`): load `history_text(session_id)` at the start
→ run the path → `add_turn(...)` at the end → the **`MEMORY · session updated`**
step in `/dev`. This is why *"is it in navy?" → "order it"* resolves across a
channel/language switch.

**Stateless by design:** the **Vision** and **Advisor** agents keep **no memory of
their own** — they receive `customer_id` + the question and pull any "memory" from
**tools** (e.g. the advisor calls `list_customer_orders` to read order history).
Fewer stateful components = fewer ways to drift or leak context between agents.

---

## 5k. Loop & runaway prevention — what stops agents looping

Agent loops (A→B→A delegation cycles, tool-call runaway, re-planning loops, retry
storms) are prevented **structurally**, not by prompt-pleading:

1. **Agent-as-tool, NOT transfer.** The orchestrator composes workers with
   `AgentTool`, so it *calls* a worker and **stays in control**; a worker
   **cannot transfer control back** to the orchestrator or sideways to a peer. The
   A→B→A cycle is **not expressible**.
2. **Workers own only function tools — no nested agents.** `tools=skill.get_tools()`
   are plain in-process functions, so a worker can't invoke another agent. Depth is
   hard-bounded: `orchestrator → ONE worker → its tools → return`.
3. **Single-pass turn.** `run_turn` runs ONE pass with **mutually-exclusive**
   branches (`checkout` **or** `adk` **or** `fallback`) — no outer loop re-feeds the
   reply into the agent.
4. **The transactional path skips the loop.** Checkout is deterministic and runs
   *before* the ADK branch, so the critical path can't loop at all.
5. **No re-planning planner on production agents.** Workers use native
   function-calling (terminates on the first non-tool response). The only
   `PlanReActPlanner` agent (the advisor) is bounded: `thinking_budget=0` +
   token cap + a **one-shot grounded synthesis fallback** that guarantees
   termination if the planner ever stalls.
6. **Bounded retries.** `AgentHarness.run(retries=1)` by default (no retry); only
   the read-only advisor uses `retries=2` (a hard, idempotent bound).
7. **Failure degrades once.** ADK error / empty → fall back to the deterministic
   engine **once**, never "retry the agent in a loop."
8. **Guardian is loop-safe.** A **circuit breaker** opens after N failures (kills
   retry storms); heal is a fixed staged sequence (DETECT→…→VERIFY), and the
   heal-forward probe runs on a **timed interval**, not a tight loop.

**CTO one-liner:** *"Loops are prevented structurally — agent-as-tool (no transfer
cycles), workers with no nested agents (bounded depth), a single-pass turn, a
deterministic transactional path outside the loop, bounded retries, degrade-once
fallback, and a circuit breaker. The only planner-based agent is capped with a
guaranteed-termination fallback."*

---

## 5l. RSI — recursive self-improvement (the CriticAgent, isolated)

GOOPHER self-heals on **two** levels: the **Guardian** heals the *infrastructure*
(circuit breaker / failover, §5e); the **CriticAgent** heals the *behaviour* — it
learns from its own failures, with **no retraining and no redeploy**. It's a
separate, isolated agent (`critic_agent.py`) that does **not** modify any existing
flow.

**The loop:**
```
👎 unsatisfactory answer (the shopper flags it in the extension)
  → record_failure (LessonStore)
  → Gemini-as-judge (gemini-2.5-flash on Vertex · google.genai · thinking_budget=0
       · JSON): failure_summary + root_cause + a CONCRETE corrective LESSON + confidence
  → store the lesson IF confidence ≥ 0.70 (confidence-gated)
  → lesson_retrieve (keyword-RAG) surfaces the top-k relevant lessons for the next
       similar query and injects them (+ a few real in-stock items) into the LLM
       directives → the next answer improves
```

| Piece | Where |
|---|---|
| Agent | `CriticAgent` — `record_failure` · `run_healing_cycle` (judge → store) · `retrieve_lessons` · `answer_with_lessons` |
| Store | `LessonStore` — Firestore (`rsi_failures` / `rsi_lessons`) in cloud, in-memory locally; keyword-RAG `retrieve(top-k)` |
| Endpoints | `POST /critic/flag` · `POST /critic/heal` · `GET /critic/lessons` · `POST /critic/answer`; dev: `GET /dev/rsi` · `POST /dev/rsi/reset` |
| Extension | **👎 Teach GOOPHER** under a reply → flag + heal → shows the lesson it wrote |
| `/dev` | an **RSI** flow card (🔎 DETECT → 🧠 JUDGE → 💡 LESSON) + an **RSI panel** (lessons learned + 🧹 Reset) |

**Isolation & safety.** The lesson injection into `/chat` is **additive and
guarded**: it only appends guidance for the LLM paths, never changes routing, the
deterministic checkout gate, or tools; it is a **strict no-op when no lesson
matches** (existing behaviour unchanged); and any RSI error is swallowed so a turn
can't break. When a lesson shapes a reply, the meta shows `lesson_retrieve` and
`/dev` shows a "💡 lesson_retrieve — applied N learned lesson(s)" step.

**Demo (before → teach → after).** Reset lessons in `/dev` → ask *"do you have
laptops?"* (flat refusal) → **👎 Teach GOOPHER** (it learns an actionable lesson) →
ask again → now it acknowledges, **names specific in-stock items** (e.g. Play-Doh,
a puzzle, the soccer ball) and asks a clarifying question.

**Production upgrade path (the slide vision).** Swap the lightweight store/retrieval
for **Vertex AI Embeddings + Vertex AI Vector Search (+ AlloyDB metadata)**, source
failures from **CCAI Insights** (low-CSAT conversations), and run the cycle as a
**Cloud Run Job every 15 min via Cloud Scheduler**. A Cloud Run Job entrypoint
(`python -m backend.app.agents.critic_agent`) is already included.

> **CTO line:** *"Two layers of self-healing — Guardian heals the infrastructure,
> the CriticAgent heals the behaviour. It critiques its own failures with
> Gemini-as-judge, writes a corrective lesson, and retrieves it via RAG for the
> next similar query. The agent improves itself — no retraining, no redeploy."*

---

## 5m. Order-confirmation email — best-effort notifications

Every placed order — **single or bulk, via text / voice / phone / camera vision /
Excel upload** — funnels through `place_order` / `place_bulk_order`. Both call
`email_tool.send_order_email(order)` **once at that choke point**, so a single hook
covers all modalities (and any future one) automatically.

**Design properties**

- **Best-effort, never blocks checkout.** The whole send is wrapped in
  `try/except` and returns a small `{sent, mode, to, detail}` dict — a mail outage
  can *never* fail an order. The order is already placed; the email is a side-effect.
- **Pluggable transport, first configured wins** (in `send_order_email`):
  1. **SMTP** — `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` (e.g. Gmail App Password).
  2. **Resend** — `RESEND_API_KEY` (free tier; a single HTTPS POST via stdlib
     `urllib`, no SDK).
  3. **Simulated** — no creds → the email is logged and surfaced in the reply
     (`📧 … (email simulated)`), so the flow and the demo work with **zero secrets**.
- **Recipient** defaults to `settings.notify_email` (`your-address@example.com`),
  overridable by `NOTIFY_EMAIL`. The body is built from the order (items, total,
  tracking, ETA).
- **Surfaced to the user.** `place_order`/`place_bulk_order` attach `data["email"]`;
  the chat reply and the extension's staged checkout render
  `📧 Order confirmation emailed to <addr>` as the final step.
- **Deployed via CI/CD env vars** (the Cloud Run deploy replaces env vars each run,
  so creds are injected from a GitHub secret in `deploy.yml`, exactly like
  `JWT_SECRET` — never committed). With the secret unset it writes `""` → simulated.

```
place_order / place_bulk_order ──► _notify_order_email(data) ──► send_order_email
        (every modality)                (best-effort)            ├─ SMTP  (smtp_*)
                                                                 ├─ Resend(resend_api_key)
                                                                 └─ simulated (default)
```

> **CTO line:** *"Order confirmations email the buyer on every channel — but the
> send is a best-effort side-effect wrapped in try/except, so a mail provider
> outage can never fail a paid order. Transport is pluggable (Resend or SMTP) and
> falls back to a logged simulation when no secret is set."*

> **Why Resend over a Gmail SMTP setup** — see [`TRADEOFFS.md` §F](TRADEOFFS.md):
> no app-password / 2FA dance, no SMTP-port egress concerns on Cloud Run, a clean
> free tier, and one stdlib HTTPS call instead of an SMTP handshake.

---

## 6. High-volume order management (Req 3)

Two entry points handle scale:
- **Conversational**: paste many `ORD-...` ids (or upload a CSV via the modality
  subagent) → orchestrator routes to `order_bulk_status`.
- **Programmatic**: `POST /orders/bulk` for back-office / batch reconciliation.

Both share `order_tool.bulk_order_status`, which caps a single request at
`settings.bulk_max_orders` and reports `found` / `missing` / `truncated` for
safe, observable batch processing.

---

## 7. Security notes

- JWT bearer auth on every non-public endpoint (T1); tokens are short-lived.
- For production, swap the demo password check for **Firebase Authentication /
  Identity Platform** (also free tier) — the token contract is unchanged.
- Container runs as a non-root user; secrets (`GOOGLE_API_KEY`, `JWT_SECRET`)
  are injected as Cloud Run env vars / GitHub secrets, never committed.
- CORS is currently `*` for demo convenience; lock to the extension origin in
  production.
