# GOOPHER — Presentation Deck (Interactive)

A slide-by-slide deck for presenting GOOPHER to **CTO**, **business stakeholders**,
and the **technical team** in one session. It's **interactive by design**: almost
every slide has a **🖱️ DO LIVE** moment (click something in the real product) or a
**💬 ASK THE ROOM** prompt — so it's a *driven demo*, not slides being read.

> **Format of each slide below:**
> - **🎯 Audience** — who this slide is mainly for
> - **🖥️ On screen** — what to show / the slide's content
> - **🎤 Say** — the spoken line(s)
> - **🖱️ Do live / 💬 Ask** — the interactive moment
> - **❓ Likely question** — and the one-line answer

---

## ⏱️ Before you start (setup checklist — 2 min)

- [ ] Cloud Run **warm**: open `…/version` (confirms the live build) and `…/dev`.
- [ ] Extension **loaded & signed in** (side panel open).
- [ ] A **real object** on the desk (soccer ball / Oreo pack) for the camera.
- [ ] **Camera OFF in your meeting app** (frees the webcam for GOOPHER).
- [ ] **Share entire screen** (so the extension + `/dev` + camera popup all show).
- [ ] Two tabs ready: **`/dev`** (developer portal) and **`/skills`** (capability map).

**Tailor on the fly:** Business room → lean on slides **1–4, 8, 10**. Technical/CTO
→ add **5, 6, 7, 9**. Whole deck ≈ **20–25 min** + Q&A.

---

## Slide 1 — Title & the hook  🚀

**🎯 Audience:** everyone
**🖥️ On screen:**
- **GOOPHER** — *one AI shopping agent: type it, say it, or show it.*
- Subtitle: *Multi-agent · multi-channel · multi-lingual · multimodal — Google ADK + Gemini 2.5 Flash on Vertex AI.*
- A single screenshot of the side panel mid-conversation.

**🎤 Say:** *"GOOPHER is a single conversational agent that lets a customer browse,
ask, and buy — by typing, talking, or showing an item to the camera — in their own
language. Everything you'll see is live, in the cloud."*

**🖱️ Do live:** Open the **GOOPHER side panel** so it's visible from slide 1.
**💬 Ask the room:** *"How many separate apps does a customer touch today to
search, get support, and check out? We're going to collapse that into one chat."*

**❓ Likely Q:** *"Is this a mock-up?"* → *"No — it's deployed on Cloud Run; I'll
show the live build version in a moment."*

---

## Slide 2 — The problem & the value  💡

**🎯 Audience:** business stakeholders / CTO
**🖥️ On screen:** three pain points → one solution:
- Fragmented: search ≠ support ≠ checkout.
- Friction: forms, SKUs, app-switching, language barriers.
- **GOOPHER:** one natural conversation, any channel, any input, any language.

**🎤 Say:** *"Retail loses customers at every hand-off. GOOPHER removes the
hand-offs — one assistant that understands 'do you have BBQ chips?' and 'order it'
in the same breath, on web or phone, by text, voice, or camera."*

**💬 Ask the room:** *"What's your customers' #1 drop-off point — search, support,
or checkout?"* (Tie their answer to a feature you'll show.)

**❓ Likely Q:** *"Why an agent vs. a chatbot?"* → *"A chatbot answers; an agent
**acts** — it checks live inventory and places real orders through a safe gate."*

---

## Slide 3 — LIVE: conversational shopping (text)  💬

**🎯 Audience:** everyone (this is the first "it's real" moment)
**🖥️ On screen:** the side panel.
**🎤 Say:** *"Let me just talk to it."*

**🖱️ Do live (script):**
1. Type **"do you have oreos?"** → real price + stock.
2. Type **"place an order of oreo cookies"** → it shows a **cart** and asks
   **"please confirm"** (nothing charged yet).
3. Click **✅ Confirm** → **Payment → Order Placed** staged receipt.

**🎤 Say (while it runs):** *"Notice it never substituted a different snack, and it
**asked me to confirm before charging**. That confirm step is everywhere — text,
voice, and camera."*

**❓ Likely Q:** *"What if the item doesn't exist?"* → *"It says so — it never
guesses or substitutes."* (Optionally demo "order a ceramic gnome".)

---

## Slide 4 — LIVE: multimodal — see it, shop it + voice  📷🎤

**🎯 Audience:** everyone (the "wow")
**🖥️ On screen:** the camera popup.
**🎤 Say:** *"Customers don't always know the product name. So — show it."*

**🖱️ Do live (script):**
1. Click **📷** → hold up the **soccer ball** → say **"what's the price?"** → it
   recognizes the *Adidas Match Soccer Ball*, speaks the price.
2. Say **"place an order"** → **preview + please confirm** → Confirm → placed.
3. (Optional) Click **🎤** and **speak** a question to show voice in / spoken answer.

**🎤 Say:** *"That's **Gemini Vision on Vertex AI** — the same model doing
recognition, reasoning, and natural language in one round trip. And it still asks
me to confirm before charging."*

**❓ Likely Q:** *"On-device or cloud?"* → *"Cloud — Gemini multimodal on Vertex;
the camera frame is sent securely to a dedicated vision endpoint."*

---

## Slide 5 — How it works: the multi-agent system  🧩

**🎯 Audience:** technical team / CTO
**🖥️ On screen:** the agent diagram + open **`/dev`** live:
- ROOT **orchestrator** (Gemini 2.5 Flash) → 4 **worker sub-agents** (inventory,
  order, checkout, fulfillment) via **agent-as-tool**.
- Each worker **picks a skill** from the **skill registry**, runs through the
  **common agent harness**, and calls **tools**.

**🎤 Say:** *"This isn't one prompt — it's a real **Google ADK multi-agent
system**. Watch the live pipeline."*

**🖱️ Do live:** In `/dev`, point at a turn: **harness → orchestrator → worker
sub-agent → agent skill → tool → memory**. Then open **`/skills`** — *"every
capability is registered, each flagged read-only or transactional."*

**🎤 Say:** *"Two foundations: a **skill registry** (capabilities agents pick by
name) and a **common harness** every agent runs through — an engineered platform,
not a pile of prompts."*

**❓ Likely Q:** *"Real ReAct agents?"* → *"The ReAct paradigm via Gemini's
**native function-calling** — more reliable than text-scratchpad ReAct."*

---

## Slide 6 — Trust by design: the transactional gate, state & loops  🔒

**🎯 Audience:** CTO / technical (the "is it safe & sane?" slide)
**🖥️ On screen:** three guarantees:
- **LLM orchestrates, code transacts** — checkout is **deterministic**, never run
  by the LLM. (Fulfillment too — owned by the order-mgmt agent, runs deterministically post-payment.)
- **State** — one durable **session memory** by `session_id` (Firestore), shared
  by all agents; vision/advisor are stateless.
- **No loops** — **agent-as-tool** (no transfer-back), bounded depth, single-pass
  turn, bounded retries, degrade-once, circuit breaker.

**🎤 Say:** *"The AI decides *to* check out; it never *executes* the payment — a
deterministic, auditable gate does. State is centralized and durable. And loops
are impossible by construction, not by prompt-pleading."*

**🖱️ Do live:** In `/dev`, point at the **`MEMORY · session updated`** step (state)
and the **deterministic checkout gate** label.

**❓ Likely Q:** *"How do you stop runaway agents?"* → *"Workers can't transfer
control back, hold no nested agents, retries are bounded, failures degrade once."*

---

## Slide 7 — Two agent styles on one model  🧠

**🎯 Audience:** technical / CTO (architectural maturity)
**🖥️ On screen:** native function-calling (transactions) **vs** explicit ReAct (advice).

**🎤 Say:** *"We use the right agent style per job."*

**🖱️ Do live:** Type **"a healthy snack under $4 that pairs with my last order"**
(or just tap **🧠** with an empty box) → show the recommendation **and** the
collapsible **"🧠 How GOOPHER reasoned (ReAct plan)"** panel: PLAN → ACTION →
REASONING → FINAL ANSWER.

**🎤 Say:** *"That's an explicit **ReAct agent** (ADK `PlanReActPlanner`) — you can
**watch it plan, act over tools, and reason**. It's **read-only** — it recommends,
never orders. Native function-calling for money; visible ReAct for advice."*

**❓ Likely Q:** *"Why not ReAct everywhere?"* → *"It adds latency, tokens, and
fragility; we keep it off the transactional path."*

---

## Slide 8 — THE FINALE: self-healing Guardian  🛡️

**🎯 Audience:** everyone (the jaw-dropper — slow down here)
**🖥️ On screen:** `/dev` Guardian panel (health LEDs + chaos buttons).

**🎤 Say:** *"What happens when a dependency fails at 2am? Watch."*

**🖱️ Do live (script):**
1. Click **💥 Kill Vertex** → LED goes red.
2. Click **▶ Vertex** (replay a request) → a purple **HEAL card** streams
   **DETECT → DIAGNOSE → REMEDIATE → VERIFY**.
3. Click **✅ Restore all** → heals forward to green. *Repeatable.*

**🎤 Say:** *"It **detects**, **diagnoses** against a playbook, **remediates** (self-
repair → retry → failover so the customer is still served), and **restores
itself**. No pager, no human. And it's **isolated** — it drives synthetic
transactions and never touches live flows, so it's 100% safe to run on stage."*

**❓ Likely Q:** *"Is that real or scripted?"* → *"Real — it's the same circuit
breaker + failover policy; the chaos button injects an actual fault."*

---

## Slide 9 — Engineering rigor & operations  ⚙️

**🎯 Audience:** CTO / technical
**🖥️ On screen:** the "production-shaped" checklist:
- **Model:** `gemini-2.5-flash` on **Vertex AI** (no OpenAI key in cloud); one
  model does reasoning, language, **and** vision.
- **Security:** single-user lockdown (allowlist + master pw, **fail-closed**), JWT,
  rate-limit + size-limit, secrets never committed.
- **Quality:** **117 unit tests + 8 evals**; **CI/CD** push→test→Cloud Build→Cloud
  Run; **CI-sim** of the production path.
- **Observability:** Cloud Trace, `/dev` portal, `/metrics`, `/version`.
- **Cost:** free-tier-first; scales to zero.

**🎤 Say:** *"It's not a prototype taped together — it's containerized,
auto-deployed, tested, observable, and self-healing."*

**🖱️ Do live:** Open **`/version`** — *"that's the exact build you're watching."*

**❓ Likely Q:** *"What's deliberately deferred?"* → *"Real SSO, Secret Manager,
tighter network lockdown, multi-user, live payments — documented with reasons."*

---

## Slide 10 — Roadmap, value recap & Q&A  🗺️

**🎯 Audience:** everyone (the close)
**🖥️ On screen:**
- **Recap (value):** one assistant · any channel/language · text+voice+camera ·
  safe checkout · self-healing · live transparency.
- **Roadmap:** multi-user + real auth → live payment/inventory integrations →
  Secret Manager + network hardening → dynamic skill selection.
- **Resources:** `DEMO.md`, `ARCHITECTURE.md`, `QUESTION-ANSWER.md`.

**🎤 Say:** *"One agent, every channel, every modality — that sees, talks, reasons,
transacts safely, and heals itself. Where would this move the needle for you
first?"*

**💬 Ask the room:** *"Which is most valuable to you — the multimodal shopping, the
safe-by-design checkout, or the self-healing reliability?"* (Let their answer shape
the follow-up.)

**❓ Open Q&A** — keep **`QUESTION-ANSWER.md`** open; it has crisp answers + "where
to point" for both technical and business questions.

---

## 🎛️ Interactivity quick-map (what to click, per slide)

| Slide | Interactive moment |
|---|---|
| 1 | Open the side panel live |
| 2 | Ask: biggest drop-off point? |
| 3 | Type a query → order → **Confirm** |
| 4 | 📷 show a real object → "order" → Confirm; 🎤 voice |
| 5 | Open `/dev` + `/skills`; trace the pipeline |
| 6 | Point at `MEMORY` step + deterministic gate |
| 7 | Tap 🧠 → show the ReAct plan panel |
| 8 | 💥 Kill Vertex → watch heal → Restore all |
| 9 | Open `/version` |
| 10 | Ask: which value matters most? |

## 🆘 If something breaks on stage
- Any live step fails → **pivot to `/dev` and the Guardian demo** (slide 8): it's
  isolated and always works, and a graceful failure *is* the reliability story.
- Camera won't open → use **"📁 Use a saved photo instead"** in the camera window.
- Cloud cold start (slow first reply) → it's warming; the next reply is instant —
  *(or pre-warm with `/version` before you start)*.

---

*Pair this with **DEMO.md** (full word-for-word script), **ARCHITECTURE.md** (deep
dive), and **QUESTION-ANSWER.md** (Q&A bank).*
