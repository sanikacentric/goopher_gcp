# GOOPHER — The Full Demo Journey (for the CTO + Customer VP)

**Audience:** a **technical stakeholder (CTO / domain expert)** and a **VP / Customer
Engineering leader**. You are the **Google Cloud Customer Engineer, Applied AI** —
lead with the outcome, prove it with depth, switch voices fluidly.

**Every beat below uses one template so it's easy to run live:**
> **SAY** (one business line) → **DO** (the exact click) → **BEHIND THE SCENES**
> (which agent + model + tools) → **POINT AT `/dev`** (what to show) →
> **CHALLENGE & TRADE-OFF** (the senior-engineer note).

**The one model behind everything:** **Gemini 2.5 Flash on Vertex AI** (via the unified
`google.genai` SDK). One model, two usage styles — native function-calling for production,
explicit ReAct for the advisor. *Why Flash:* low latency + low cost + strong tool use; we set
`thinking_budget=0` on short, structured calls so the answer never gets starved.

**Golden line (repeat all day):** *"The LLM orchestrates and converses; deterministic
Python transacts — AI experience with enterprise control, on Google Cloud."*

> **Pre-flight:** warm Cloud Run (`/version`), sign in, real object on the desk, `/dev` +
> `/skills` tabs open, RSI lessons reset, mic permission granted, email inbox open.

---

## PART A — THE LIVE JOURNEY (7 beats, ~12 min)

### Beat 1 · TEXT — a simple question (the easy win)
- **SAY:** "Let's start how a customer would — just ask a question."
- **DO:** type **"do you have oreo cookies?"** → Send.
- **BEHIND THE SCENES:**
  - `main.py` (FastAPI) authenticates the call (JWT).
  - **Deterministic pre-process** (no LLM): `modality_agent` (text) → `language_agent` (English)
    → `channel_agent` (web) → **load session memory** from Firestore.
  - **ROOT `goopher_orchestrator`** (ADK **LlmAgent**, **Gemini 2.5 Flash / Vertex**) decides this
    is a catalog question and delegates to the **`inventory_agent`** worker (**agent-as-tool**).
  - The worker picks the **`inventory` skill** → calls the **`inventory_search`** tool →
    reads the **mock retail DB (Firestore)** → grounded answer (real price + stock).
- **POINT AT `/dev`:** show the live card top-to-bottom: `AUTH → PRE-PROCESS → AGENT HARNESS →
  ORCHESTRATOR → WORKER SUB-AGENT (inventory_agent) → AGENT SKILL → TOOL → MEMORY`. "Every step
  is traced — this is how you run AI in production, not a black box."
- **CHALLENGE & TRADE-OFF:** *Challenge:* a full sentence ("do you have…") used to fail exact-substring
  search. *Fix:* tokenized scoring + department detection in `database.py`. *Trade-off:* we accept
  ~4–5 LLM calls/turn (cost/latency) **in exchange for visible, real agent orchestration** — the thing
  the brief asked us to prove. Deterministic pre-processing keeps the cheap work off the LLM.

### Beat 2 · TEXT — place an order (safety + the email)
- **SAY:** "Now the hard part everyone gets wrong — letting AI *act* on an order, safely."
- **DO:** type **"can you please order oreo cookies"** → a **cart preview** appears with
  **🟡 'Please confirm — should I place this order?'** → click **✅ Confirm order**.
- **BEHIND THE SCENES:**
  - The orchestrator detects a **purchase intent**, so it routes to the **DETERMINISTIC CHECKOUT
    GATE** (`_try_checkout`) — **the LLM does NOT place the order.**
  - Step 1 returns a **preview** (no charge). On Confirm, the **`checkout_agent`** path runs
    `checkout_tool`: **cart → `process_payment` → persist `ORDER_PLACED`**, then the
    **`order_management_agent`** runs the **9-stage fulfillment** pipeline (`order_mgmt_tool`).
  - **`email_tool`** sends a confirmation email (best-effort, **Resend** free tier) — **show the
    real email arriving** in the inbox.
- **POINT AT `/dev`:** the `EMAIL` step (cyan) — *"order confirmation emailed to …"* — and the
  9-stage fulfillment card.
- **CHALLENGE & TRADE-OFF:** *Challenge:* early on the LLM was put in the transactional path and **lost
  the cart**. *Decision:* a deterministic gate with **confirm-before-charge** and **no substitution**.
  *Why:* an AI must never charge a card or swap an item — safety & auditability beat flexibility.
  *Email trade-off:* it's a **best-effort side-effect after the order commits** (try/except), so a mail
  outage can never fail a paid order. *(War-story:* the email 403 was a **Cloudflare User-Agent block**,
  not auth — we read the error *body*, not the status.)

### Beat 3 · BULK ORDER — CSV/Excel upload (enterprise + human-in-the-loop)
- **SAY:** "B2B buyers don't chat item-by-item — they send a purchase order. Watch."
- **DO:** 📎 attach **`enterprise_bulk_order_goopher.xlsx`** (or a `.csv`) → type **"place a bulk
  order from the attached file"** → a **multi-line cart preview** appears → **✅ Confirm** →
  staged receipt → **email**.
- **BEHIND THE SCENES:**
  - `_try_file_bulk_order` detects the format (xlsx is a **binary ZIP** → parsed with **openpyxl**;
    csv/txt handled too), `_parse_tabular` reads the **product_name / sku / quantity** columns,
    resolves each line **by SKU first, then name** (**never substitutes**), and builds **one bulk order**.
  - **Human-in-the-loop:** it **previews and waits for Confirm** — identical safety to typed/voice.
    Confirm re-sends the resolved SKUs (`__bulk_confirm__`), so the file isn't re-uploaded.
  - Same `checkout_agent` → `order_management_agent` → **email** path as Beat 2.
- **POINT AT `/dev`:** the bulk checkout card (exact items + quantities, e.g. Cheez-It ×50,
  Coca-Cola ×120, Lay's ×200) + the email step.
- **CHALLENGE & TRADE-OFF:** *Challenge:* an `.xlsx` decoded as text gave garbage → it silently fell
  back to a default basket. *Decision:* **branch on the file's real format and parse it**; add a test
  asserting the parsed items. *Why:* "know your bytes" — a binary isn't text; and a silent fallback hides
  the real failure. *Trade-off:* added `openpyxl` as a dependency to gain reliable enterprise PO ingestion.

### Beat 4 · ADVISOR — recommendations you can *watch think* (explicit ReAct)
- **SAY:** "Beyond answering, GOOPHER advises — and you can see it reason."
- **DO:** tap **🧠 (Advisor)** or type **"recommend items based on my last order"** → a
  recommendation + a collapsible **PLAN → ACT → REASON** panel.
- **BEHIND THE SCENES:**
  - The **`shopping_advisor`** is the **only explicit-ReAct agent** — ADK `LlmAgent` with
    **`PlanReActPlanner`** on **Gemini 2.5 Flash**. It **plans → searches inventory/order history →
    reasons → recommends.**
  - It is handed **only read-only skills** (asserted in code) → it can **recommend but never buy**.
- **POINT AT `/dev`:** the `advise` card — harness → ReAct agent → read-only skills → tools.
  "Two agent styles on **one** model: native function-calling for transactions, explicit ReAct for advice."
- **CHALLENGE & TRADE-OFF:** *Challenge:* 2.5-Flash "thinking" starved the final answer ("plan but no
  answer"); and it once recommended the *same* item the customer just bought. *Decision:*
  `thinking_budget=0` + a grounded synthesis safety net, and recommend **other** items in the same
  department near the price. *Trade-off:* ReAct is more transparent but less predictable, so we keep it
  **off the transactional path** — read-only only.

### Beat 5 · MIC — voice input (multimodal #1)
- **SAY:** "Same brain, hands-free."
- **DO:** click **🎤**, say **"do you have potato chips?"** (or "place an order of oreos").
- **BEHIND THE SCENES:**
  - `mic.js` uses the browser **Web Speech API** (speech-to-text); the transcript goes through the
    **exact same** orchestrator pipeline as typed text. Replies are spoken back via `speechSynthesis` (TTS).
  - Memory is shared, so context carries between voice and text seamlessly.
- **POINT AT `/dev`:** same pipeline card, `modality = voice`.
- **CHALLENGE & TRADE-OFF:** *Challenge:* the first words were dropped and a spoken "confirm order" was
  treated as a brand-new request. *Decision:* keep the mic "warm" and intercept confirmations locally.
  *Trade-off:* browser STT (free, zero infra) now; **clear path to CCAI / Speech-to-Text** for contact-center scale.

### Beat 6 · VISION — "see it, shop it" (multimodal #2, the wow)
- **SAY:** "Now the new conversion surface — show a product to the camera."
- **DO:** click **📷**, hold up the **soccer ball**, ask **"what's the price?"** → then **"place an
  order"** → **Confirm**.
- **BEHIND THE SCENES:**
  - The **`vision_agent`** sends the image + prompt to **Gemini 2.5 Flash (multimodal) on Vertex**
    (`generate_content([image, prompt])`) → recognizes the item → prices it from the catalog.
  - Ordering goes through the **same checkout gate** → **confirm-before-charge** (parity with text/voice).
- **POINT AT `/dev`:** the vision turn + the checkout/confirm steps.
- **CHALLENGE & TRADE-OFF:** *Challenge:* Vision returned empty (wrong SDK, then "thinking" ate the
  budget) and originally **charged on capture**. *Decision:* unified `google.genai` + `thinking_budget=0`
  + add confirm-before-charge to the camera path too. *Why:* a safety invariant is only real if it holds
  on **every** modality.

### Beat 7 · CHANNEL — switch to Phone (voice) (multichannel)
- **SAY:** "Same agent, any channel — here's the mobile experience."
- **DO:** **Channel → Phone (voice)** → the panel re-skins as a **phone simulator**; ask anything;
  optionally switch **Language → Spanish** and order in Spanish.
- **BEHIND THE SCENES:**
  - `channel_agent` adapts formatting (`adapt_for_phone`, voice-safe text); it's the **same backend**,
    a visual skin — **multichannel without forking logic**.
  - **Multilingual:** a non-English order is translated to English **just for the deterministic gate**
    (so confirm-before-charge still fires), and the **reply + email are localized back** to the customer's
    language. `language_agent` uses `¿/¡` as a decisive Spanish signal.
- **POINT AT `/dev`:** `channel = phone`, `language = es`, and the localized confirm/email.
- **CHALLENGE & TRADE-OFF:** *Challenge (great war-story):* a Spanish order **skipped confirm and replied
  in English** — four stacked bugs ending in **language mis-detection**. *Decision:* fix detection first
  (top of the pipeline), translate-for-the-gate, localize back. *Why:* a guardrail enforced by **English
  keywords isn't a guardrail in other languages.** *Trade-off:* one extra translate call per non-English
  order — gated so plain questions stay fast.

---

## PART B — THE PLATFORM (the "is this production-grade?" deep-dive)

### 8 · Consistent memory — how context is kept
- **What:** one **session store keyed by `session_id`**, **loaded at the start** of every turn and
  **persisted at the end**. It holds history + language + channel + last-viewed item.
- **Why it works across switches:** because it's centralized, the customer can go text → voice → phone →
  another language and GOOPHER still knows "order **it**" / "the above item".
- **Where it lives:** **Firestore in the cloud** (durable, shared) / SQLite locally.
- **CHALLENGE & TRADE-OFF:** an in-process dict **loses context** when Cloud Run scales or scales-to-zero.
  *Decision:* Firestore-backed session memory. *Trade-off:* a tiny read/write per turn for **durable,
  multi-instance context** — the right call for serverless.
- **SAY:** *"It remembers the conversation no matter the channel or language — that's what makes it feel
  like one assistant, not five bots."*

### 9 · The orchestrator — which one and why
- **What:** a **real Google ADK `LlmAgent`** named **`goopher_orchestrator`** on **Gemini 2.5 Flash /
  Vertex**, using **native function-calling**. It delegates to **four worker sub-agents — wired as
  `AgentTool`s (agent-as-tool, NOT transfer-back).**
- **Why agent-as-tool:** **loops are impossible by construction** (no agent can hand control back into a
  cycle) — not "prevented" by prompt-begging.
- **CHALLENGE & TRADE-OFF:** ADK let the model **skip** sub-agents, and a `SequentialAgent` **can't** be an
  `AgentTool`. *Decision:* deterministic pre-processing + agent-as-tool workers. *Trade-off:* more LLM
  calls than a single prompt, **bought** for visible, controllable orchestration + Cloud Trace.

### 10 · Google Cloud — why deployment is easy + which models
- **Models:** **Gemini 2.5 Flash on Vertex AI** (managed, IAM-scoped, **no training on your data**).
  Optional **Gemma** (open weights) via **Model Garden** for on-device / data-residency.
- **Runtime:** **Cloud Run** — serverless, **scale-to-zero** (near-$0 idle), autoscales on spikes,
  one-command deploy.
- **Data + ops:** **Firestore** (serverless DB), **Cloud Trace + Logging** (observability),
  **Secret Manager / IAM** (secrets & access).
- **CI/CD:** push to `main` → **GitHub Actions → Cloud Build → Cloud Run** (env vars / secrets injected
  at deploy). A `/version` marker confirms exactly what's live.
- **CHALLENGE & TRADE-OFF:** the deploy **replaces** env vars each run, so secrets (JWT, Resend) come from
  GitHub secrets, never committed. *Why:* reproducible, secure releases. *Cost trade-off:* scale-to-zero
  means an occasional cold start — narrated as **graceful degradation** (the fallback engine still answers).
- **SAY:** *"It's deployed today on the **free tier / $300 credit** — we prove value at near-zero cost,
  then scale on the same managed services."*

### 11 · The database — which and why
- **What:** a **repository** abstraction — **Firestore in the cloud**, **SQLite locally** (zero-setup dev).
- **Why Firestore:** serverless (no ops), durable, **shared across Cloud Run instances** (critical with
  scale-to-zero), holds catalog + orders + `ORDER_PLACED` + session memory.
- **CHALLENGE & TRADE-OFF:** keeping the catalog in sync — auto-seed from `goopher_catalog.json` on boot,
  preserving runtime orders. *Trade-off:* a thin repository layer so the **same code** runs on SQLite or
  Firestore — testable offline, production-grade in the cloud.

### 12 · Agent foundations (the platform mindset)
GOOPHER isn't a pile of agents — it's a small **platform**: a **common harness** (one runtime),
a **skill registry** (a capability catalog with guardrails), named **sub-agents**, and **tools**.
"Adding a new agent is **fast and safe** because the scaffolding and safety are shared."

### 13 · Agent Harness (scaffolding)
- **What:** `AgentHarness` — **every** agent (orchestrator, workers, advisor) runs through it:
  **build → ADK session → run-loop → collect (text/tool-calls/observations) → resilience
  (retry/degrade-once) → `AgentRunResult`.**
- **Why:** one tested, observable run-loop instead of copy-pasted boilerplate in N places.
- **CHALLENGE & TRADE-OFF:** the ADK path **isn't testable in CI** (no creds), so we added a **CI-sim**
  that blocks the `google.*` packages and runs everything through the deterministic fallback — proving
  the refactor is safe. *Trade-off:* extra test machinery for confidence on a path CI can't run live.

### 14 · Agent Skills (the registry)
- **What:** `agent_skill_registry` — skills are registered **once** (instruction + tools); an agent
  **picks a skill by name**; each skill carries a **`read_only` flag enforced in code** and exposed at
  **`GET /skills`**.
- **Why:** capabilities are **separate from agents** and reusable; the advisor is **provably** read-only.
- **SAY:** *"Sub-agents and skills are different layers — and safety (read-only) is enforced by code, not by hope."*

### 15 · Security
- **What:** **JWT** on every call; **email allowlist + master password**, **fail-closed**; **rate +
  request-size limits**; **CORS**; secrets in **Secret Manager / env**, **never committed** (`.env`
  gitignored; keys rotated on any leak).
- **For the demo it's single-user (`demo@goopher.app`).** Production upgrade path: real identity
  (Firebase Auth / IdP), VPC-SC, network IAM.
- **SAY:** *"An agent that touches orders must be trustworthy — locked down, fail-closed, and auditable."*

### 16 · Self-healing + Recursive Self-Improvement (two kinds of "gets better")
- **Guardian — self-healing infrastructure (the finale).** A deterministic **synthetic** monitor (no LLM)
  that drives **probe** transactions — **never live flows.** In `/dev`, **💥 break a dependency**
  (Vertex / catalog / fulfillment) and watch **DETECT → DIAGNOSE → REMEDIATE → VERIFY** stream as a HEAL
  card, with a circuit breaker. *"That's the reliability story your SLA needs — proven live."*
- **CriticAgent — recursive self-improvement (RSI).** **Gemini-as-judge** (NOT an ADK agent, NOT ReAct):
  on a **👎**, it sends the failed conversation to a single structured Gemini call → `{root_cause, lesson,
  confidence}`; confidence-gated lessons go to a **`LessonStore`** (Firestore); the next similar question
  **retrieves the lesson via keyword-RAG** and the orchestrator **additively injects** it. **No retrain,
  no redeploy.**
- **CHALLENGE & TRADE-OFF:** "learned ≠ applied" — a stored lesson that never shapes generation only *looks*
  like a loop. *Decision:* wire **retrieve → inject** (additive, no-op when nothing matches) and give the
  demo a **reset** for a clean before→teach→after arc. *Why:* keep it **isolated** so it can't break working
  flows; integrate its output as a guarded enhancement.
- **SAY:** *"Two kinds of getting better: the **Guardian heals the infrastructure**, the **Critic improves
  the behaviour** — both visible, both live."*

---

## Close to a pilot (the CE move)
"You've seen it **act safely**, in **any language and channel**, **learn from feedback**, and **heal
itself** — deployed on Google Cloud you already trust. Proposed next step: a **4–6 week pilot** on a slice
of your real catalog, **2–3 agreed success metrics** (deflection %, conversion lift, CSAT), on the
**free tier / $300 credit**. If it hits the metrics, we expand channels (CCAI voice) and departments.
**Shall we scope that pilot?"**

> Mechanics & exact buttons: `DEMO.md` · One-page tour + diagram: `CODE-TOUR.md` ·
> CE objection-handling & value: `CE-DEMO.md` · Trade-offs: `TRADEOFFS.md` · War-stories: `LEARNINGS.md`.
