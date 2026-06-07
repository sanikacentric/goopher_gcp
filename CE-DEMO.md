# GOOPHER — Customer Engineer (Applied AI/ML) Demo Playbook

**Your role in the room:** you are the **Google Cloud Customer Engineer, Applied AI**.
You are not "showing your project" — you are a trusted technical advisor who **understood
the customer's problem, designed a solution on Google Cloud, and brought a working
prototype to de-risk it.** Lead with *their* outcome; prove it with depth on demand.

**The CE arc:** Discovery → Frame the business problem → Map to Google Cloud →
Demo *value* (not features) → Handle objections with depth → Quantify the value →
Close to a pilot. Talk **business to the VP, architecture to the domain expert** — switch fluidly.

> Repeat all day: *"The LLM orchestrates and converses; deterministic code transacts —
> so you get AI experience with enterprise control, on Google Cloud you already trust."*

---

## 0 · Open like a CE (30s)
"Thanks for the time. Based on what your team shared, the goal is **modern self-service
shopping — chat and voice, any language, that can actually act on orders, safely**. I've
built a working prototype on Google Cloud — **GOOPHER** — so we can talk architecture *and*
see it run, not just slides. Before I dive in — **what does success look like 12 months out?**"
*(Ask, listen, then tie every beat back to their answer. That single question is the most
"CE" thing you can do.)*

## 1 · Frame the business problem (the "why now") (1m)
"Off-the-shelf chatbots fail here because the job is **four hard things at once**: it must
**act** on live inventory/orders, **route** to specialists while keeping context, speak
**every channel and language**, and keep money-moving actions **safe and auditable**. Get any
one wrong and you erode trust. That combination is exactly where **Applied AI on Google Cloud**
earns its place."

## 2 · Map the requirements → Google Cloud (the CE core skill) (2m)
Say: *"Here's how each requirement maps to a managed Google Cloud capability — so you're
buying a platform, not a science project."*

| Customer need | Google Cloud product | CE value point |
|---|---|---|
| Reasoning / conversation | **Gemini 2.5 Flash on Vertex AI** | fast, low-cost, **no training on your data**, enterprise IAM |
| Multi-agent orchestration | **Google ADK** (Agent Development Kit) | real sub-agents + tools, the supported path — not a bespoke framework |
| Run it / scale it | **Cloud Run** (serverless) | **scale-to-zero** → pay only for use; scales to spikes automatically |
| Memory / catalog / orders | **Firestore** (serverless) | durable shared context across channels; no DB to manage |
| Trust & visibility | **Cloud Trace + Logging** (+ live `/dev` portal) | audit every agent action; debug in production |
| Voice / phone at scale | path to **Conversational Agents / CCAI** | today: web + phone simulator; clear roadmap to contact-center |
| Data residency / on-device | **Vertex Model Garden + Gemma** (open weights) | private/edge option without re-architecting |
| Secrets / governance | **Secret Manager · IAM · VPC-SC** | enterprise security posture |

"All of it runs in the **free tier / $300 credit** for the pilot — so we prove value at near-zero cost."

## 3 · The demo — sell the OUTCOME at each beat (8–10m)
*Narrate the business value first, then click. (Mechanics live in `DEMO.md`.)*

| Beat | Click | CE value line |
|---|---|---|
| **See-it-shop-it** | 📷 show the soccer ball → price → order | "Camera commerce — **multimodal Gemini** turns 'what is this?' into a purchase. New conversion surface." |
| **Safe checkout** | "place an order of oreos" → **Please confirm** → Confirm | "The AI never charged a card — a **deterministic gate** did, after confirmation. **Auditable, no wrong orders.**" |
| **Enterprise Excel PO** | upload the `.xlsx` → preview → confirm | "B2B buyers drop in a purchase order; we parse, match by SKU, confirm, place one bulk order. **Self-service at enterprise scale.**" |
| **Any language** | ask in Spanish → confirm → **Spanish email** | "Same safety and confirmation **in the customer's language** — global reach, one system." |
| **Radical transparency** | open **/dev**, trace one turn | "Every agent step is visible and traced — **this is how you operate AI in production**, not a black box." |
| **It learns** | 👎 Teach → re-ask → better answer | "**Recursive self-improvement** — it critiques its own miss and applies the lesson next time. **No retrain, no redeploy.**" |
| **THE FINALE: self-healing** | /dev → 💥 Kill Vertex → watch it heal → Restore | "Break a dependency live; it **detects, diagnoses, remediates, verifies** itself. **That's the reliability story your SLA needs.**" |

## 4 · Objection handling (this is where CEs win) (have ready)
| They say | You say (depth + reassurance) |
|---|---|
| "Will the AI place wrong/unwanted orders?" | "It **can't** — purchases go through a deterministic gate with **confirm-before-charge** on every channel, and it **never substitutes**. The LLM proposes; code commits." |
| "LLM cost at scale?" | "**Gemini 2.5 Flash** is low-cost; deterministic pre-processing handles intent/routing **without** an LLM call; **Cloud Run scales to zero**; and a grounded fallback keeps us running during spikes/quota. We size cost per conversation in the pilot." |
| "Data privacy / our data training the model?" | "**Vertex AI does not train on your data.** Single-tenant, IAM-scoped, secrets in Secret Manager. For residency/edge we can run **Gemma** open-weights in Model Garden — same code path." |
| "Vendor lock-in?" | "**ADK is open**, the model is config-swappable (provider abstraction; Gemma open weights), and it's standard Cloud Run + Firestore. Portable by design." |
| "Hallucinations / accuracy?" | "Answers are **grounded in tool results** (no inventing prices/stock); the **CriticAgent (LLM-as-judge)** corrects misses; and **145 tests + evals gate every change** in CI/CD." |
| "Will it scale / stay up?" | "Cloud Run autoscales, Firestore is serverless, bulk endpoints handle volume, and the **self-healing Guardian** degrades gracefully instead of failing." |
| "How long to value?" | "It's **already deployed**. A scoped pilot on your catalog is weeks, not quarters." |

## 5 · Quantify the value (talk to the VP) (1m)
Frame outcomes (co-create the numbers with them in the pilot):
- **Deflection** — self-service resolves routine order/status asks → lower support cost.
- **Conversion** — camera + recommendations + instant answers → higher basket/attach.
- **Reach** — multilingual + multichannel → serve segments you can't staff for.
- **Trust & risk** — auditable, confirm-before-charge, never-substitute → fewer disputes.
- **Reliability** — self-healing → protects revenue during incidents.
- **TCO** — serverless scale-to-zero + Flash → cost tracks usage, not headcount.

## 6 · Close to a pilot (the CE always closes) (30s)
"Proposed next step: a **4–6 week pilot** on a slice of your real catalog — we wire your
inventory/orders, agree on **2–3 success metrics** (deflection %, conversion lift, CSAT),
run it on the **free tier/$300 credit**, and review the data together. If it hits the metrics,
we expand channels (CCAI voice) and departments. **Does that pilot shape work for your team?"**

---

## CE soft-skills reminders (the difference between dev and CE)
- **Discovery first.** Ask "what does success look like?" / "where does this hurt today?" — then tailor.
- **Sell outcomes, not features.** Every click ends in a *business* sentence.
- **Two audiences, one breath.** Architecture for the expert, value for the VP — switch on the fly.
- **Objections are buying signals.** Welcome them; answer with depth + a reassurance.
- **Always be mapping** every need to a **named Google Cloud product**.
- **De-risk and close.** You brought a working prototype *and* a pilot plan — that's the CE move.

*(Mechanics & exact clicks → `DEMO.md`. Architecture diagram & file tour → `CODE-TOUR.md`.
Trade-offs → `TRADEOFFS.md`. War-stories → `LEARNINGS.md`.)*
