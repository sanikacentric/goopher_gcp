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

---

## 3. Components & requirement mapping

| Component | File(s) | Requirement |
|-----------|---------|-------------|
| Chrome extension "GOOPHER" | `extension/` (MV3, side panel) | **2A** |
| Customer authentication | `backend/app/auth/auth.py`, `/auth/*` | **T1** |
| ADK orchestrator | `backend/app/agents/orchestrator.py` | **T2** |
| Memory agent (context) | `backend/app/memory/memory_agent.py` | **T3**, global |
| Agent skills | `backend/app/agents/skills/*` | **T4** |
| MCP tools (inventory/order) | `backend/app/mcp/*` | **T5**, 2A-1, 2A-2 |
| Gemini LLM (free tier) | `config.gemini_model`, orchestrator | **T6** |
| Google Cloud stack (free tier) | Firestore + Cloud Run + Cloud Trace | **T7**, T14 |
| Channel subagent (phone/web) | `backend/app/agents/channel_agent.py` | **2A-4** |
| Language subagent | `backend/app/agents/language_agent.py` | **2A-5** |
| Modality subagent | `backend/app/agents/modality_agent.py` | **2A-6** |
| Individual + high-volume orders | `order_tool.bulk_order_status`, `/orders/bulk` | **3** |
| Self-service GenAI front end | extension + `/chat` | **4** |
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
