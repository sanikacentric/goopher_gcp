# 🎬 GOOPHER — CTO Demo Script & WOW Lines

A ready-to-present walkthrough. Each section has **what to do**, **what they'll
see**, and the **exact line to say**. Total runtime ≈ 8–10 minutes; every section
also works standalone.

> **Live service:** `https://goopher-api-7vnucwimtq-uc.a.run.app`
> **Dev portal:** `…/dev`  ·  **Storefront:** `…/`  ·  **Extension:** GOOPHER side panel

---

## ✅ Pre-flight checklist (5 min before)
- [ ] Extension reloaded to **v0.5.0** (`chrome://extensions` → version shows 0.5.0)
- [ ] Signed into GOOPHER (`demo@goopher.app` / your master password)
- [ ] **Camera OFF in Google Meet** (frees the webcam for GOOPHER)
- [ ] **Share entire screen** (so the camera popup + `/dev` are visible)
- [ ] **Headphones on** (clean voice — mic won't echo GOOPHER's TTS)
- [ ] `order.txt` ready + a backup soccer-ball photo saved locally
- [ ] `/dev` open in a tab; `/version` shows `2026-06-01-guardian` (or later)
- [ ] Warm the service: do one action a minute before so there's no cold start

---

## 0. The opener (15 sec)
> *"GOOPHER is a production-grade conversational retail agent — a Chrome
> extension backed by a Google ADK + Gemini multi-agent service on Cloud Run.
> It's multi-channel, multi-lingual, multi-modal, and — the part I'm most proud
> of — it's **self-healing**. Let me show you."*

---

## 1. 🎥 Camera Vision — "see it, shop it"
**Do:** In GOOPHER, leave the box empty → click 📷 → show a **soccer ball** → say
*"what's the price?"* → Capture. Then *"place an order"* → Capture → **it shows a
cart and asks "please confirm"** → tap **✅ Confirm** (or say *"confirm order"*).

**They see:** Gemini Vision recognizes the *Adidas Match Soccer Ball*, speaks the
price, then — like text and voice — **previews the cart and asks to confirm**
before charging, then runs the staged cart → ORDER PLACED.

> 🗣️ *"I'm showing a real-world object to the camera. **Gemini Vision on Vertex
> AI** recognizes it, maps it to our catalog, and acts on what I said — by voice.
> No barcodes, no SKUs. And note it **asks me to confirm before charging** — the
> same safe confirm-before-pay step we have for typed and spoken orders."*

> 💡 WOW line: *"This is the same Gemini multimodal model doing recognition,
> reasoning, and natural-language response — in one round trip."*

---

## 2. 🛒 Structured checkout — "the LLM is not the cashier"
**Do:** Type *"order me a soccer ball"* → Send. Open the 🛒 orders panel.

**They see:** 🛒 cart → 💳 processing → ✅ payment → 🎉 ORDER PLACED, then the
order in the panel.

> 🗣️ *"Notice a design decision: the LLM understands and converses, but the
> **purchase itself runs through a deterministic, audited gate** — structured
> cart, simulated payment, a real `ORDER_PLACED` write, staged receipt. We keep
> the model out of the money path. It's the guardrail pattern: **LLM orchestrates,
> deterministic code transacts.** That's how you get an agent that's correct,
> reproducible, and audit-ready."*

---

## 3. 📄 Bulk order from a file — incl. an enterprise Excel PO
**Do:** Attach an **Excel** purchase order (`enterprise_bulk_order_goopher.xlsx`,
with `product_name` / `sku` / `order_quantity` columns) → *"place a bulk order from
the attached file"* → Send. *(A plain `order.txt` or `.csv` works too.)*

**They see:** GOOPHER parses the spreadsheet, matches every line to the live catalog,
then **previews the cart and asks "please confirm"** — e.g. 9 items at the exact
quantities (Cheez-It ×50, Coca-Cola ×120, Lay's ×200, …), subtotal ~$5,282. Click
**Confirm** → staged receipt → **📧 "Order confirmation emailed to …"**.

> 🗣️ *"A buyer drops in an enterprise Excel PO — product names, SKUs, quantities.
> We parse it with openpyxl, match every line by SKU (never substitute), **preview
> for approval**, and place ONE structured bulk order through the same deterministic
> gate. An .xlsx is binary, so we parse it — not guess at text. That's the multimodal
> 'files' requirement, at enterprise scale."*

> 💡 **Two beats to call out:** (1) the **confirm-before-charge** step is identical
> across text, voice, camera, AND file; (2) **every** placed order — any modality —
> emails the buyer a confirmation (best-effort, never blocks checkout).

---

## 4. 📱 Multi-channel — the mobile simulator
**Do:** Switch **Channel → Phone (voice)**.

**They see:** the chat reskins as a **mobile-device simulator** (bezel, status
bar, home indicator); everything still works.

> 🗣️ *"Same agent, channel-aware. On **Web** it's the side panel; switch to
> **Phone** and you get the mobile experience with voice and camera — and the
> backend tailors replies for voice automatically. One agent, every channel."*

---

## 5. 📊 The Developer Portal — radical transparency
**Do:** Open `/dev`. Run any GOOPHER action and point at the live feed.

**They see:** every turn streamed in real time — auth → preprocess → ORCHESTRATOR
→ worker sub-agents → tools → memory → reply, plus the 9-stage fulfillment
pipeline and a real `ORDER_PLACED` write.

> 🗣️ *"This isn't a mock. Every turn is traced live — you can see the
> orchestrator pick a worker sub-agent, the tools fire, the fulfillment pipeline
> run, and a real database row get written. Full observability, built in."*

### 5b. 🧠 Durable memory — point at the `MEMORY · session updated` step
**Do:** Ask *"what's the price of the tiered midi dress?"* → then just *"is it in
**navy**?"* → then *"**order it**."* Point at the last pipeline step,
`MEMORY · session updated`.

**They see:** the agent resolves *"it"* correctly across turns; each turn's
pipeline ends with `MEMORY · session updated · persisted user + assistant turns`.

> 🗣️ *"Every turn **loads prior context** at the start and **persists the new
> turn** at the end — to **Firestore** in the cloud, so it's durable and shared
> across Cloud Run instances even after scale-to-zero. That's why I can say 'is
> it in navy?' then 'order it' and it knows what 'it' is. It also remembers
> **language and channel** — start on Web in English, continue on Phone in
> Spanish, same thread. Real, durable conversational memory."*

> 💡 WOW line: *"This is the T3 'context-across-switches' requirement — the agent
> has genuine memory, and you can watch it save every turn live."*

### 5c. 🗣️ Contextual ordering — "order it" / "order the above item"
**Do:** Ask about a product (e.g. *"do you have oreos?"*). Then just say
*"order it"* — or *"place an order of the above 10 items."*

**They see:** GOOPHER orders **the exact product you were just looking at** (10 ×
Oreo), not a random item — because it remembers the last item you viewed.

> 🗣️ *"Watch — I ask about a product, then I just say 'order it.' It remembers
> what I was looking at and orders exactly that. That's contextual memory turning
> conversation into action."*

> ⚠️ Guardrail to mention: *"If I'd never looked at anything, it asks 'which
> item?' rather than guessing — and it never substitutes the wrong product. And
> the quantity ('10') never bleeds into product matching."*

---

### 5d. 🧠 Two agent styles — native tool-calling **and** explicit ReAct
**Do:** Easiest — **leave the box empty and tap 🧠**; it recommends from your last
order. (Or type a specific ask like *"a healthy snack under $4 that pairs with the
cookies I ordered last time"* and tap **🧠** — **not** Send.)

**They see:** a short bulleted recommendation **matched to the last order's
department and price** (a $17.99 toy → other toys ~≤ $18, not random snacks), plus
a collapsible **"🧠 How GOOPHER reasoned (ReAct plan)"** panel showing
**PLAN → ACTION → REASONING → FINAL ANSWER** — the agent looking up the order
history, searching inventory, filtering by price, and explaining its pick.

> 🗣️ *"Everything so far used **native function-calling agents** — fast,
> reliable, and what we use for anything that moves money. But for open-ended
> advice I run an **explicit ReAct agent** — ADK's `PlanReActPlanner` on the same
> Gemini 2.5 Flash — and you can **watch it plan, act over tools, and reason**.
> It's **read-only** — it recommends, it never places an order. We pick the right
> agent style per job, and keep ReAct strictly **off the transactional path**."*

> 💡 Why this lands: it shows architectural maturity — you didn't just reach for
> ReAct because it's trendy; you chose **native tool-calling for transactions**
> and **visible ReAct for reasoning**, deliberately. (Backed by
> `ARCHITECTURE.md §5f`; isolation proven in `tests/test_advisor_agent.py`.)

---

### 5e. 🗂 The agent foundations — skill registry + common harness (optional, for technical CTOs)
**Do:** In a browser tab, open **`/skills`** (e.g. `…/skills`).

**They see:** every agent skill as JSON — `name`, `title`, `description`,
`read_only`, and its tools — the live capability map.

> 🗣️ *"Under the agents are two foundations. One, an **agent skill registry** —
> every capability registered once, and agents **pick skills by name**. Each skill
> is flagged read-only or transactional, so our read-only advisor is **provably**
> unable to pick a place-order tool. Two, a **common agent harness** — one runtime
> that every agent runs through: build → session → run → collect → resilience →
> structured result. So all our agents share one tested, observable scaffold —
> adding a new agent is just `AgentHarness(build_agent=…).run(...)`."*

> 💡 Why this lands: it signals an **engineered platform**, not a pile of prompts —
> a registry of capabilities + a shared, resilient runtime. (`ARCHITECTURE.md`
> §5g, §5h; tests in `test_agent_skill_registry.py`, `test_agent_harness.py`.)

---

### 5f. ❓ Likely CTO questions — crisp answers

**"That fulfillment pipeline — which agent runs it?"**
> *"It's the **order-management agent's** capability — its `fulfillment` skill and
> `run_fulfillment` tool, the 9 stages from validation to invoice. But for a real
> purchase it fires **deterministically the instant payment succeeds**, from the
> checkout gate — not as an LLM step. The agent owns it; deterministic code runs
> it. That's why it's reliable and auditable."* (`ARCHITECTURE.md` §5i)

**"How do the agents maintain state?"**
> *"One **session memory** keyed by `session_id`, durable in **Firestore** in the
> cloud, shared by every conversational agent — turn history plus working-memory
> facts like the last item viewed. The ADK harness keeps a parallel session under
> the same key. Vision and the advisor are **stateless** — they pull memory from
> tools. So state is centralized and durable, not scattered per agent."* (point at
> the **`MEMORY · session updated`** step in `/dev`; `ARCHITECTURE.md` §5j)

**"How do you stop the agents looping?"**
> *"Structurally. The orchestrator uses **agent-as-tool**, so a worker returns a
> result and **can't transfer control back** — an A→B→A cycle isn't even
> expressible. Workers hold only function tools (no nested agents), each turn is a
> **single pass**, checkout is **deterministic** (outside the loop), retries are
> **bounded**, failures **degrade once** to a deterministic engine, and the
> Guardian's **circuit breaker** stops retry storms."* (`ARCHITECTURE.md` §5k)

---

### 5g. 🧠 Recursive self-improvement (RSI) — the agent learns from its own failure
**Setup:** in `/dev`, click **🧹 Reset lessons** (so the "before" is a clean baseline).

**Do (the before → teach → after arc):**
1. Ask **"do you have laptops?"** → a **flat** refusal: *"We don't carry laptops."*
2. Click **👎 Teach GOOPHER** under that reply.
3. Ask **"do you have laptops?"** again → now it's **proper**: acknowledges, **names
   specific in-stock items** (e.g. Play-Doh $8.49, a puzzle $10.49, soccer ball
   $17.99) and asks a clarifying question.

**They see (in `/dev`):** an **RSI** card — **🔎 DETECT → 🧠 JUDGE (Gemini-as-judge) →
💡 LESSON STORED** — plus the **RSI panel** showing the lesson it wrote; on the
re-ask, the turn shows **💡 lesson_retrieve — applied 1 learned lesson**.

> 🗣️ *"GOOPHER has **two layers of self-healing**: the Guardian heals the
> infrastructure; this **CriticAgent** heals the behaviour. It just **critiqued its
> own failure** with Gemini-as-judge, wrote a corrective lesson, stored it, and on
> the next question **retrieved it via RAG** to answer better. The agent improved
> itself — **no retraining, no redeploy**. In production this runs as a **Cloud Run
> Job every 15 minutes** sourced from **CCAI Insights**, backed by **Vertex AI
> Vector Search**."*

> 💡 Why this lands: most "AI agents" are static. This one **gets better on its
> own** — a recursive-self-improvement loop you can watch close, live. Isolated &
> safe: the lesson only *adds* guidance, never changes checkout/routing.
> (`ARCHITECTURE.md` §5l; `critic_agent.py`; tests in `test_critic_agent.py`.)

---

## 6. 🛡️ THE FINALE — the self-healing Guardian (the jaw-dropper)
> This is the closer. Slow down and let it land. It's **isolated** — it drives
> synthetic transactions and touches no live flow, so it's 100% safe to run live.

### 📍 Where the buttons are
The **💥 Kill Vertex** button is in the **Developer Portal** (`…/dev`), **not** the
extension. Just under the colored legend you'll see the **🛡️ Guardian —
self-healing** panel:
- a row of health LEDs: 🧠 Gemini/Vertex AI · 🗄️ Catalog · 📦 Order fulfillment
- below them, the controls:
```
💥 Inject fault:  [ Kill Vertex ]  [ Corrupt catalog ]  [ Fail fulfillment ]
▶ Run request:    [ Vertex ]       [ Catalog ]          [ Fulfillment ]
                                                          [ ✅ Restore all ]
```
"Kill Vertex" is the first **red-outlined** button under **💥 Inject fault**. It's
pinned at the **top** of `/dev`, above the live feed — scroll up if needed. If you
don't see it, confirm `…/version` is `2026-06-01-guardian` (or later) and
hard-refresh (Ctrl+F5).

### 🔁 The 4 self-healing steps (what streams into the purple HEAL card)
A 4-step loop wrapped in a circuit breaker:
1. **🔎 DETECT** — the protected op fails; Guardian catches it, marks the
   component 🟠 healing, bumps the breaker. → `1. DETECT — vertex.synthetic_request failed: ChaosError…`
2. **🧠 DIAGNOSE** — classifies the fault against a playbook (root cause), doesn't
   retry blindly. → `2. DIAGNOSE — LLM provider unavailable (Vertex 5xx / empty / timeout)`
3. **🔧 REMEDIATE** (escalating, stops at the first that works): self-repair (e.g.
   re-seed) → retry with backoff → fail over so the customer is still served. →
   `retry #1 failed → retry #2 failed → failover (customer unaffected)`
4. **✅ VERIFY** — set the state: recovered on primary → 🟢; serving via failover →
   🟠 (degraded but up), keep probing. → `4. VERIFY — serving via failover; probing to heal forward`

Wrapped by **⚡ circuit breaker** (after N failures, open the circuit and serve the
fallback directly) and **🔄 heal forward** (a background probe restores the primary
and closes the circuit once the fault clears — autonomously).

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

**Do, step by step (≈90 sec):**
1. On `/dev`, point at the **🛡️ Guardian health strip** — all 🟢.
   > *"Guardian continuously watches our critical dependencies — the LLM, the
   > data layer, fulfillment. All green."*
2. Click **💥 Kill Vertex**. The Vertex LED turns 🟠, badge → **HEALING**.
   > *"Watch — I'm going to take down our LLM provider. In production this is a
   > 2 a.m. page."*
3. Click **▶ Vertex** (a shopper request hits the down subsystem).
   > *"A customer request comes in while Vertex is down…"*
4. A **HEAL** card streams live: `DETECT → DIAGNOSE → REMEDIATE (retry → retry →
   failover, "customer unaffected") → VERIFY`.
   > *"It **detected** the outage, **diagnosed** the root cause, **retried**, then
   > **failed over** so the customer is served anyway — and **verified** the
   > recovery. The shopper never saw an error."*
5. Click **✅ Restore all**. A second HEAL card: `PROBE → HEAL FORWARD ("primary
   is back → closed the circuit")`. Strip returns to 🟢.
   > *"And when the provider recovers, its background probe **heals forward** —
   > restores the primary and closes the circuit. Autonomously."*

**The mic-drop line:**
> 🎤 *"It detected, diagnosed, fixed, and verified — with **no pager and no
> human**. And here's the kicker: these aren't hypothetical failures. Vertex
> outages, the Gemini thinking-budget bug, a stale catalog, rate limits — we hit
> **every one of these** building this. The agent now resolves them itself."*

**If asked "is it real or scripted?":**
> *"It's a real circuit-breaker + failover engine — the same patterns you'd put
> in a production service. The chaos button is a controlled fault injector, like
> Netflix's Chaos Monkey, so I can demonstrate it on demand. And it's a **separate,
> isolated agent** — it runs synthetic transactions, so it can demonstrate
> recovery without any risk to the live shopping flows."*

---

## 7. Close (15 sec)
> *"So: one agent, every channel, every modality — see-it-shop-it vision,
> structured and audited checkout, full live observability, and a self-healing
> layer that keeps it up. All on Google Cloud free tiers, with CI/CD and 86
> passing tests behind it."*

---

## 🧯 If something misbehaves live (graceful saves)
| If… | Say / do |
|---|---|
| Camera won't open | *"Let me use a saved photo"* → click **📁 Use a saved photo instead** in the camera window. |
| Recognition misses | Capture once more with the item centered/lit; or fall back to text: *"order a soccer ball."* |
| A request is slow | *"That's a cold start on the free tier — first call wakes the container."* Re-send. |
| Anything errors | Pivot to `/dev` and the Guardian demo — it's isolated and always works. |

---

## 🎯 One-sentence summaries (pick per audience)
- **Engineer CTO:** *"LLM orchestrates, deterministic code transacts, and a
  circuit-breaker/failover Guardian self-heals — with live traces to prove it."*
- **Product CTO:** *"Customers shop by showing an item to the camera and talking;
  the system never breaks in front of them."*
- **Business CTO:** *"Production-grade agent on free-tier infra, with autonomous
  recovery that removes 2 a.m. pages."*

---

## 🤖 The model story (if the CTO asks "what models?")
- **Production runs on one model: `gemini-2.5-flash` on Vertex AI.** It does the
  multi-agent reasoning, the multilingual replies, **and** the camera Vision —
  one natively-multimodal model, on the $300 Vertex credit / free-tier.
- **`gpt-4o-mini` (OpenAI)** is wired as a **swappable fallback** (`LLM_PROVIDER`)
  but isn't used in the cloud — no key set there.
- **The LLM never executes a transaction.** Checkout, fulfillment, and the
  Guardian self-healing are deterministic code; the model only understands and
  phrases. That's the "LLM orchestrates, code transacts" guardrail.

> 🗣️ *"One model — Gemini 2.5-flash on Vertex AI — handles reasoning, language,
> and vision. OpenAI is a one-flag fallback. And the model never touches the
> money path: purchases run through deterministic, audited code."*

---

## ✅ Requirements coverage (use if the CTO asks "is everything done?")
Every acceptance criterion is implemented, deployed, and tested (**145 passing**).

| # | Criterion | Status / where to show it |
|---|---|---|
| 2A | Chrome extension (MV3 side panel) | the GOOPHER side panel |
| 2A-4 | Multi-channel (web / phone) | Channel dropdown → **phone simulator** |
| 2A-5 | Multi-lingual | ask in Spanish; auto-detect + dropdown |
| 2A-6 | Multi-modal (text / voice / image / **camera vision**) | 🎤 voice, 📷 camera, 📎 file |
| T1 | Authentication + **single-user lockdown** (fail-closed) | sign-in; allowlist + master pw |
| T2 | ADK orchestrator + worker sub-agents | `/dev` ORCHESTRATOR → workers; Cloud Trace |
| T3 | Memory / context across switches | `MEMORY · session updated`; "order it" |
| T4 | Agent skills | `agents/skills/` |
| T5 | Tools (in-process function tools) | inventory / order / checkout tools |
| T6 | Gemini LLM (free tier / Vertex) | `gemini-2.5-flash` |
| T7 | Google Cloud free tier | Firestore + Cloud Run + Trace |
| T8 | Evals | `python evals/run_evals.py` |
| T9 | Unit tests | `pytest` — 145 passing |
| T10 | Observability + **dev portal** + **self-healing Guardian** | `/dev`, Cloud Trace, `/metrics`, `/version` |
| T11 / T12 | README / Architecture | `README.md`, `ARCHITECTURE.md` |
| T14 / T16 | Production-grade, Dockerized, Cloud Run | live URL |
| T15 | Commented code | throughout |
| T17 | CI/CD (GitHub Actions) | push → test → build → deploy |
| 3 | Individual **& high-volume** orders (chat, `/orders/bulk`, **file upload**) | bulk order from `order.txt` |
| 4 | Self-service ordering — single + **structured checkout gate** | "place an order"; staged cart |
| 5 | Order management — 9-stage fulfillment → `ORDER_PLACED` | `/dev` fulfillment pipeline |
| Sec | Abuse protection (rate limit + request-size limits) | `middleware.py` |
| ✨ | **Self-healing** (circuit breaker · failover · chaos · heal-forward) | `/dev` 🛡️ Guardian — the finale |

---

## 🧩 Code walkthrough — "show the code, sound senior"

**How to use this section live.** Open the file in your editor as you talk. For each
file there's a **TECH** line (say this to the domain expert) and a **SAY** line
(the same thing for the VP / customer). Golden thread to repeat:
> *"The LLM orchestrates and converses; deterministic Python transacts. Every agent
> runs through one common harness, picks named skills, and is fully observable."*

### Agent-type cheat-sheet (memorize this)
GOOPHER uses **four different patterns on purpose** — not everything is an "agent":

| Pattern | Who | Why |
|---|---|---|
| **LlmAgent + native function-calling** | the ROOT orchestrator + 4 workers | reliable tool use on the transactional path (ReAct *paradigm*, done implicitly) |
| **LlmAgent + `PlanReActPlanner` (explicit ReAct)** | the Shopping **Advisor** only | read-only, multi-hop reasoning you want to *show* (the 🧠 plan panel) |
| **LLM-as-judge** (no ADK, no ReAct) | the **CriticAgent** (RSI) | a single structured Gemini call that grades a bad answer → a lesson |
| **Deterministic Python (no LLM)** | pre-processors, the checkout gate, tools, the Guardian | speed, safety, auditability — no intelligence needed |

### Master map — every Python file, one line each
| File | Role | Agent type | Calls Gemini? | Key tools / calls |
|---|---|---|---|---|
| `agents/orchestrator.py` | ROOT brain `goopher_orchestrator` + the whole turn pipeline | **LlmAgent** (native function-calling) | **Yes** — Gemini 2.5 Flash on **Vertex** via `google.genai`/ADK | delegates to 4 workers (agent-as-tool); deterministic `_try_checkout` gate; `_to_english`/`_localize`; RSI inject |
| `agents/advisor_agent.py` | Shopping Advisor (recommendations) | **LlmAgent + `PlanReActPlanner`** (explicit ReAct), **read-only** | **Yes** — Gemini 2.5 Flash, `thinking_budget=0` | read-only skills (inventory, order); `_synthesize_recommendation` safety net |
| `agents/critic_agent.py` | **RSI** — learn from 👎 feedback | **LLM-as-judge** (not ADK, not ReAct) | **Yes** — `client.models.generate_content` (JSON, Vertex) | `LessonStore` (Firestore/in-memory), keyword-RAG `retrieve`, heuristic fallback |
| `agents/guardian.py` | **Self-healing** infra monitor | Deterministic (no LLM) | No | circuit breaker + chaos; DETECT→DIAGNOSE→REMEDIATE→VERIFY on **synthetic** probes |
| `agents/vision_agent.py` | Camera "see-it-shop-it" | Multimodal Gemini call | **Yes** — `generate_content([image, prompt])`, Vertex | recognizes item → price → confirm-before-charge |
| `agents/modality_agent.py` | Detect text/voice/image; pull ORD-ids | Deterministic (no LLM) | No | regex/string parsing |
| `agents/language_agent.py` | Detect language + force reply language | Deterministic heuristic | No | `detect_language` (`¿`/`¡` = Spanish), `language_directive` |
| `agents/channel_agent.py` | Web vs phone formatting | Deterministic (no LLM) | No | `channel_directive`, `adapt_for_phone` |
| `agents/harness/agent_harness.py` | **Common scaffolding** for ALL agents | Runtime wrapper | (runs whatever agent it's given) | build → ADK session → run-loop → collect → resilience → `AgentRunResult` |
| `agents/skills/agent_skill_registry.py` | **Skill registry** (single source of truth) | Data + lookup | No | `AgentSkill` (carries `read_only`), `get_tools`, `read_only_skill_names` |
| `agents/skills/{inventory,order,checkout,order_mgmt}_skill.py` | One capability each (instruction + tools) | Config | No | the tool list an agent picks by name |
| `tools/checkout_tool.py` | **Transaction** (cart→pay→persist) | Deterministic (no LLM) | No | `place_order`, `place_bulk_order`, `process_payment`, `_notify_order_email` |
| `tools/email_tool.py` | Order-confirmation email | Deterministic (no LLM) | No | `send_order_email` → SMTP / **Resend** / simulated; `localize` callable |
| `tools/order_mgmt_tool.py` | 9-stage fulfillment pipeline | Deterministic (no LLM) | No | `run_fulfillment` (validation→ORDER_PLACED→…→invoice), streams to `/dev` |
| `tools/inventory_tool.py` | Catalog search / stock | Deterministic (no LLM) | No | `search_inventory`, `check_stock`, `get_product_details` |
| `tools/order_tool.py` | Order status / history / bulk | Deterministic (no LLM) | No | `get_order_status`, `list_customer_orders`, `bulk_order_status` |
| `db/database.py` | Repository (SQLite local / **Firestore** cloud) | Data layer | No | `search_products` (tokenized scoring + department detection) |
| `observability/flow_recorder.py` | Live `/dev` pipeline cards | Tracing | No | `TurnTrace`, `FlowRecord` |
| `observability/telemetry.py` | Cloud Trace + metrics + logs | Tracing | No | `log_event`, spans, `incr` |
| `models/schemas.py` | Pydantic request/response models | Types | No | validation/serialization |
| `config.py` | Settings | Config | No | `gemini_model`, `use_vertexai`, `notify_email`, SMTP/Resend |
| `main.py` | FastAPI app (all endpoints + storefront + `/dev`) | API | No | `/chat`, `/vision`, `/advise`, `/critic/*`, `/orders/bulk`, `/catalog`, `/skills`, `/version` |

### The five files to actually open on stage

**1) `agents/orchestrator.py` — the brain.**
- **TECH:** A real ADK `LlmAgent` (`goopher_orchestrator`) on **Gemini 2.5 Flash via Vertex** (`google.genai`). It uses **native function-calling**, not a ReAct planner, and delegates to four worker `LlmAgent`s wired as **`AgentTool`s (agent-as-tool, no transfer-back)** — that's why loops are impossible by construction. Before the LLM, deterministic Python handles modality/language/channel/memory; a deterministic **`_try_checkout` gate** does every purchase (cart → payment → `ORDER_PLACED`) so the model never moves money. Multilingual orders are translated to English for the gate (`_to_english`) and the reply/email localized back (`_localize`) — both via `_llm_text` → a Vertex `google.genai` client.
- **SAY:** *"This is the manager. It understands the customer, decides which specialist to ask, and converses — but it is never allowed to charge a card. A separate, rule-based module does the actual transaction, so it's safe and auditable."*

**2) `agents/advisor_agent.py` — the only explicit ReAct agent.**
- **TECH:** `LlmAgent(planner=PlanReActPlanner())` on Gemini 2.5 Flash. It **plans → acts over tools → reasons → recommends**, and is handed **only read-only skills** from the registry (asserted in code), so it can never get a checkout tool. `thinking_budget=0` fixes 2.5-Flash's "plan but no answer" stall; `_synthesize_recommendation` is a grounded safety net.
- **SAY:** *"This is the personal shopper. You can literally watch it think — plan, look things up, reason, and suggest. By design it can recommend but never buy."*

**3) `agents/critic_agent.py` — recursive self-improvement (RSI).**
- **TECH:** **Not** an ADK agent and **not** ReAct — it's **Gemini-as-judge**: a deterministic class that, on a 👎, sends the failed conversation to `client.models.generate_content` (JSON, `thinking_budget=0`) and gets back `{failure_summary, root_cause, lesson, confidence}`. Confidence-gated (≥0.70) lessons go to a `LessonStore` (Firestore `rsi_lessons` / in-memory). On the next turn the orchestrator does **keyword-RAG** (`retrieve_lessons`) and **additively injects** the lesson into its directives — no retrain, no redeploy. Falls back to a heuristic lesson when Gemini is offline.
- **SAY:** *"When a customer says 'that wasn't helpful,' GOOPHER critiques its own answer, writes itself a lesson, and applies it the next time someone asks something similar. It gets better on its own — no engineering cycle required."*

**4) `agents/guardian.py` — self-healing infrastructure.**
- **TECH:** A deterministic **synthetic monitor** (no LLM) that drives **probe** transactions — it never touches live customer flows. Chaos buttons in `/dev` break a dependency (Vertex / catalog / fulfillment); the Guardian runs **DETECT → DIAGNOSE → REMEDIATE → VERIFY** with a circuit breaker and streams each step as a purple HEAL card.
- **SAY:** *"If a dependency goes down at 2 a.m., the system notices, diagnoses, and recovers itself — and we can prove it live by breaking something on stage and watching it heal."*

**5) `agents/harness/agent_harness.py` + `skills/agent_skill_registry.py` — the foundations.**
- **TECH:** Every agent (orchestrator, workers, advisor) runs through **one** `AgentHarness` (build → session → run-loop → collect → resilience → `AgentRunResult`) instead of copy-pasted boilerplate. **Skills** are registered once; an agent **picks a skill by name**; each skill carries a `read_only` flag enforced in code and exposed at `GET /skills`.
- **SAY:** *"We built it like a platform: one reusable runtime for every agent, and a catalog of capabilities with guardrails baked in — so adding a new agent is fast and safe."*

### The UI — "is it a gradient or JavaScript?" (both, intentionally no framework)
- **Storefront** (`site/`): semantic **HTML** + **pure CSS** (`store.css` — CSS **gradients**, CSS grid, responsive, *no framework*) + **vanilla JavaScript** (`store.js` fetches `GET /catalog` and renders product cards). Product images are **real, self-hosted photos** in `site/img/` (hand-verified) shown Amazon-style on white tiles, with ratings + Add-to-Cart.
- **Extension** (`extension/`): Chrome **MV3 side panel** — `sidepanel.html` + `sidepanel.css` (**dark theme with Google-brand-color CSS gradients**) + **vanilla `sidepanel.js`** (login, chat, staged checkout, confirm-before-charge, RSI "Teach", advisor panel). `mic.js` uses the **Web Speech API** (speech-to-text) and `speechSynthesis` (text-to-speech); `camera.js` uses `getUserMedia` for vision.
- **TECH:** No React/Vue — plain HTML/CSS/JS for **zero build step, tiny bundle, instant load**, which is ideal for an MV3 side panel. Styling is CSS gradients; the four Google colors live on the brand mark and accents, with calm Google-blue on the action buttons.
- **SAY:** *"The store and the assistant are deliberately lightweight — they load instantly and look like a polished retail product, themed in Google's colors."*

### 🆕 What's new this session (mention if asked "what changed?")
- **Excel/CSV bulk orders** (`openpyxl`) → parse → match by SKU → **preview & confirm** → one structured bulk order (`orchestrator._parse_tabular`, `_try_file_bulk_order`).
- **Confirm-before-charge on EVERY path** — text, voice, phone, camera, **and file/xlsx**.
- **Order-confirmation email** on every order (`tools/email_tool.py`) — best-effort, **Resend** (free tier) or SMTP, localized to the customer's language; shown in `/dev`.
- **Multilingual orders fully wired** — non-English purchases now hit the confirm gate and get a localized reply + email (`_to_english`/`_localize`, `language_agent` `¿/¡` detection).
- **RSI now applies to order-intent queries too** ("can u order laptops" → learns → suggests in-stock alternatives).
- **Advisor** recommends *other* items in the same department near the price (never the item just bought).
- **Storefront**: real product photos, ratings, Add-to-Cart, no agent branding.
- **Extension**: black theme with **Google brand colors**; visible phone simulator; Advisor button in Google colors.
- **War-stories to tell** (great for "tell me about a hard bug"): a 403 that was a **Cloudflare User-Agent block** (not auth); a Spanish order that bypassed confirm because of a **four-layer bug** ending in language mis-detection; `/cola/` matching **"cho​cola​te"**. All in `LEARNINGS.md` §3.30–3.33.
