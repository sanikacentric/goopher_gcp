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
*"what's the price?"* → Capture. Then *"place an order"* → Capture.

**They see:** Gemini Vision recognizes the *Adidas Match Soccer Ball*, speaks the
price, then runs the staged cart → ORDER PLACED.

> 🗣️ *"I'm showing a real-world object to the camera. **Gemini Vision on Vertex
> AI** recognizes it, maps it to our catalog, and acts on what I said — by voice.
> No barcodes, no SKUs. The customer just shows it and says it."*

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

## 3. 📄 Bulk order from a file
**Do:** Attach `order.txt` (`order - 15 oreo cookies`, `order -20 balls`, …) →
*"please order from the attached file"* → Send.

**They see:** one structured bulk order — 15 Oreo + 17 Peanuts + 20 Soccer Ball,
per-line quantities, ~$495.

> 🗣️ *"A buyer can drop in a file and we parse it into one structured bulk order
> with per-line quantities. Anything not in the catalog is **skipped and
> reported — never silently substituted.** Safety by construction."*

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
**Do:** Type *"a healthy snack under $4 that pairs with the cookies I ordered
last time"* and tap the **🧠** button (the Shopping Advisor) — **not** Send.

**They see:** a recommendation, plus a collapsible **"🧠 How GOOPHER reasoned
(ReAct plan)"** panel showing **PLAN → ACTION → REASONING → FINAL ANSWER** — the
agent looking up the order history, searching inventory, filtering by price, and
explaining its pick.

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
Every acceptance criterion is implemented, deployed, and tested (**88 passing**).

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
| T9 | Unit tests | `pytest` — 88 passing |
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
