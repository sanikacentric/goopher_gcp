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
│   │  ADK ORCHESTRATOR  goopher_orchestrator (root LlmAgent, Gemini) [T2]      │ │
│   │  SELECTS a worker sub-agent and DELEGATES — owns NO retail tools itself.  │ │
│   │                                                                          │ │
│   │   ├─ delegates → inventory_agent ──owns──► search_inventory / check_stock│ │
│   │   │                                        / get_product_details   [2A-1]│ │
│   │   ├─ delegates → order_agent     ──owns──► get_order_status /            │ │
│   │   │                                        list_customer_orders /        │ │
│   │   │                                        bulk_order_status   [2A-2, R3] │ │
│   │   ├─ delegates → language_agent  (multi-lingual localization)    [2A-5]  │ │
│   │   └─ delegates → channel_agent   (web / phone formatting)        [2A-4]  │ │
│   │                                                                          │ │
│   │  Modality routing (text/voice/image/file)               [2A-6]          │ │
│   │  Memory (session context across switches)               [T3 / global]   │ │
│   │  Deterministic fallback engine (no-LLM backup path)                     │ │
│   │  Observability: Cloud Trace + structured logs + /metrics [T10]          │ │
│   │  Dev portal /dev — live end-to-end flow visualizer (SSE)                │ │
│   └───────────────┬──────────────────────────────────────────────────────────┘ │
│                   │ worker sub-agents call ADK function tools (in-process) [T5] │
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
   ├─ 1. Memory.get(session_id)            ← recall prior context  [T3]
   ├─ 2. modality_agent  (text/voice/image/file → text + intent)   [2A-6]
   ├─ 3. language_agent  (detect/honor language)                   [2A-5]
   ├─ 4. channel_agent   (web vs phone style)                      [2A-4]
   ├─ 5. record user turn in memory
   │
   ├─ 6. Generate reply via the ADK delegation hierarchy:
   │        invoke_agent goopher_orchestrator   (root — selects worker)
   │          └─ invoke_agent inventory_agent   (or order_agent)
   │               └─ execute_tool search_inventory   (worker owns the tool)
   │          └─ generate_content gemini-2.5-flash    (compose reply)
   │      Fallback (no LLM): deterministic intent router → tools → template
   │
   ├─ 7. channel_agent.adapt_for_phone (if phone)  ← strip markdown [2A-4]
   ├─ 8. record assistant turn in memory (Firestore in cloud)
   │
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
2. **Deterministic fallback** — intent routing over the same MCP tools, used
   automatically when the API key or ADK package is absent.

This is why unit tests and evals run offline in CI in seconds, and why a
transient LLM outage degrades to still-useful, grounded answers instead of a
hard failure.

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
