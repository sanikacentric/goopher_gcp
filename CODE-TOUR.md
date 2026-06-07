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

### Decisions I made & why (what made it successful)
**Architecture calls (lead with these):**
1. **LLM orchestrates, code transacts** — purchases go through a *deterministic* gate, not the model.
   *Why:* safety + auditability; an LLM must never be able to charge a card or substitute an item.
2. **Agent-as-tool, not agent-transfer** — workers are `AgentTool`s the orchestrator calls.
   *Why:* loops become impossible *by construction*, not by prompt-begging.
3. **Don't make everything an "agent"** — modality/language/channel are plain Python; ReAct only for the
   read-only Advisor; Critic is LLM-as-judge. *Why:* match the pattern to the job → speed, cost, reliability.
4. **One common harness + a skill registry** — every agent shares the runtime; skills carry a `read_only`
   flag enforced in code. *Why:* platform thinking — adding an agent is fast *and* safe.
5. **Best-effort side-effects** — email is wrapped in try/except *after* the order commits.
   *Why:* a mail outage must never fail a paid order.
6. **Isolate new agents** (Vision/Advisor/Guardian/Critic) so they can't touch working flows.
   *Why:* ship innovation without risking what already works.

**"Tell me about a hard bug" — bug → decision → why (`LEARNINGS.md` §3.30–3.33):**
1. **Order email 403.** Looked like auth; reading the **response body** showed Cloudflare error **1010**
   (a User-Agent block). **Decision:** send a real `User-Agent` header + *always log the error body*, not
   just the status. **Why:** a status code can be the **CDN/WAF talking, not your app** — the body has the truth.
2. **Spanish order skipped confirm-before-charge.** Four stacked bugs; the real root was **language
   mis-detected as English** (so the whole multilingual path never ran). **Decision:** add a decisive
   `¿/¡` Spanish signal, **translate→English for the gate**, localize the reply/email back — and *check the
   top of the pipeline first.* **Why:** a guardrail enforced by English keywords **isn't a guardrail in other
   languages**; verify the earliest assumption (detection) before fixing downstream.
3. **Store showed Coke for KIND & Oreo.** `/cola/` matched the substring in **"cho​cola​te"**.
   **Decision:** word-boundary the regex (`/coca|\bcola\b|\bsoda\b/`) and add a mapping test for every product.
   **Why:** substring matching is a classic trap — **assert the mapping**, don't eyeball it.
4. **Multilingual translation silently no-op'd in the cloud.** It used the legacy `google.generativeai`
   SDK, which **can't reach Vertex**. **Decision:** route all raw LLM text calls through the unified
   **`google.genai` Vertex client** (the one Vision/Critic already used). **Why:** **cloud ≠ local** for SDKs —
   use the one that works in production, and log when a client is unavailable.

**The through-line to say out loud:** *"I optimized for safety, observability, and matching each pattern to
the job — and when something broke, I read the actual evidence and fixed the earliest cause, not the symptom."*
