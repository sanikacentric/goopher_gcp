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

---

## 6. 🛡️ THE FINALE — the self-healing Guardian (the jaw-dropper)
> This is the closer. Slow down and let it land. It's **isolated** — it drives
> synthetic transactions and touches no live flow, so it's 100% safe to run live.

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
