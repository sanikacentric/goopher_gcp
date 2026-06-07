# GOOPHER — One-Page Code Tour (keep open during the interview)

**Golden line:** *"The LLM orchestrates and converses; deterministic Python transacts.
Every agent runs through one common harness, picks named skills, and is fully observable."*

---

### Architecture at a glance (point at this while you narrate)
```
                              CHROME MV3 SIDE PANEL  (vanilla JS · dark Google theme)
                              text · voice · phone · 📷 camera · 📄 file        STOREFRONT (site/)
                                            │  HTTPS + JWT                       HTML/CSS/JS · /catalog
                                            ▼
 ┌──────────────────────────────────  main.py · FastAPI (Cloud Run)  ──────────────────────────────────┐
 │  auth (allowlist + master pw, fail-closed) · rate/size limits · CORS                                 │
 │                                                                                                      │
 │  DETERMINISTIC PRE-PROCESS (no LLM):  modality_agent · language_agent · channel_agent · load memory  │
 │                                            │                                                         │
 │            purchase? ── yes ──►  ▌DETERMINISTIC CHECKOUT GATE▐  (checkout_tool: cart→pay→ORDER_PLACED │
 │                │                  "LLM is NOT the cashier"      → order_mgmt 9-stage → 📧 email)      │
 │                no                                                                                     │
 │                ▼                                                                                      │
 │        AgentHarness  ──►  ROOT  goopher_orchestrator   (ADK LlmAgent · Gemini 2.5 Flash · Vertex)    │
 │        (build→run→                     │ agent-as-tool (no transfer ⇒ no loops)                       │
 │         collect→        ┌──────────────┼──────────────┬───────────────────┐                          │
 │         resilience)     ▼              ▼              ▼                   ▼                            │
 │                  inventory_agent  order_agent   checkout_agent   order_management_agent               │
 │                         │ picks a SKILL (registry · read_only flag) → calls in-process TOOLS          │
 │                         ▼                                                                             │
 │                 mock retail DB ── Firestore (cloud) / SQLite (local)                                  │
 │                                                                                                      │
 │  + RSI lesson injected (keyword-RAG)        every step ─►  flow_recorder → /dev  +  Cloud Trace       │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘
        ▲ feeds lessons                    ▲ heals dependencies
   CriticAgent (RSI)                  Guardian (self-healing)        Advisor (explicit ReAct, read-only)
   Gemini-as-judge → LessonStore     synthetic probes · chaos        + Vision (multimodal Gemini)
            ── the 4 ISOLATED agents (never touch the working flows) ──
```

---

### One request, end to end (trace this in `/dev` while you talk)
`extension (JS)` → `main.py` (FastAPI: JWT + rate/size limits) → **deterministic pre-process**
(modality / language / channel / **load memory**) → **purchase? → deterministic checkout gate**
(skips the LLM) → else **AgentHarness** → **ROOT orchestrator (Gemini 2.5 Flash · Vertex)** picks
**ONE worker via agent-as-tool** → worker picks a **registry skill** → calls **in-process tools** →
**mock DB (Firestore)** → channel-format → **persist memory** → stream back → **Cloud Trace + /dev**.

---

### 4 patterns (say "not everything is an agent — on purpose")
| Pattern | Who | Why |
|---|---|---|
| LlmAgent + **native function-calling** | orchestrator + 4 workers | reliable tools on the money path |
| LlmAgent + **`PlanReActPlanner`** (explicit ReAct) | **Advisor** only | show the plan; read-only |
| **LLM-as-judge** (no ADK, no ReAct) | **Critic / RSI** | grade a bad answer → a lesson |
| **Deterministic Python (no LLM)** | pre-process · checkout · tools · Guardian | speed, safety, audit |

---

### Open this file → say this
| File | One-liner |
|---|---|
| `agents/orchestrator.py` | **The manager.** Real ADK LlmAgent on **Gemini 2.5 Flash / Vertex**; native function-calling; 4 workers as **AgentTools (no transfer → no loops)**; deterministic `_try_checkout` gate (LLM never charges); `_to_english`/`_localize` for any language. |
| `agents/advisor_agent.py` | **The personal shopper.** Only **explicit ReAct** (`PlanReActPlanner`); **read-only skills only** (asserted in code); `thinking_budget=0`; you can *watch it think*. |
| `agents/critic_agent.py` | **Self-improvement (RSI).** **Gemini-as-judge** (not ADK/ReAct) → JSON lesson, confidence ≥0.70 → `LessonStore` → keyword-RAG injected next turn. **No retrain, no redeploy.** |
| `agents/guardian.py` | **Self-healing infra.** Deterministic **synthetic** monitor (never touches live flows); chaos buttons → DETECT→DIAGNOSE→REMEDIATE→VERIFY. |
| `agents/vision_agent.py` | **See-it-shop-it.** Multimodal `generate_content([image, prompt])` on Vertex; **confirm-before-charge**. |
| `agents/harness/agent_harness.py` | **One runtime for every agent**: build→session→run→collect→resilience→`AgentRunResult`. |
| `agents/skills/agent_skill_registry.py` | **Skill catalog.** Agents pick skills by name; each has a `read_only` flag enforced in code (`GET /skills`). |
| `tools/checkout_tool.py` | **The cashier (code, not LLM):** cart → `process_payment` → persist `ORDER_PLACED` → email. |
| `tools/order_mgmt_tool.py` | **9-stage fulfillment** pipeline streamed to `/dev`. |
| `tools/email_tool.py` | Order email — **Resend** (free) / SMTP / simulated; best-effort, never blocks checkout; localized. |
| `db/database.py` | Repository — **SQLite local / Firestore cloud**; tokenized `search_products`. |
| `main.py` | FastAPI: `/chat /vision /advise /critic/* /orders/bulk /catalog /skills /dev /version`. |

**Deterministic helpers (no LLM):** `modality_agent` (modality + ORD-ids) · `language_agent`
(`¿/¡` = Spanish, `language_directive`) · `channel_agent` (`adapt_for_phone`).

---

### UI — "gradient or JavaScript?" → **both, no framework**
- **Storefront** `site/`: HTML + **pure CSS** (gradients/grid) + **vanilla JS** (`store.js` ← `GET /catalog`); **real self-hosted photos** in `site/img/`.
- **Extension** `extension/`: MV3 side panel — `sidepanel.css` (**dark, Google-brand-color gradients**) + **vanilla `sidepanel.js`**; `mic.js` = Web Speech (STT/TTS); `camera.js` = `getUserMedia`. *No React → zero build, instant load.*

---

### Numbers to quote
**145 unit tests** + evals (CI gates every change) · **1 Gemini model** (2.5 Flash) · **2 agent styles** ·
**4 workers + 4 isolated agents** (vision, advisor, guardian, critic) · **9-stage** fulfillment ·
confirm-before-charge on **5** input paths (text/voice/phone/camera/file) · scale-to-zero on Cloud Run.

### "Tell me about a hard bug" (war-stories — `LEARNINGS.md` §3.30–3.33)
1. Order email **403 = Cloudflare User-Agent block**, not auth — *read the error body, not the status.*
2. Spanish order skipped confirm: **four stacked bugs** ending in **language mis-detection** — *verify the top of the pipeline first.*
3. Store showed Coke for KIND/Oreo: `/cola/` matched **"cho​cola​te"** — *word-boundary your regexes.*
