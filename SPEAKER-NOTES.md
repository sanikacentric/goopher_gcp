# GOOPHER — Speaker Notes (one-pager)

**Format:** 30 min present + 10–15 min Q&A (45 min total). Audience: **Domain Expert
(technical)** + **VP of Strategy (business)**. Deliverable: a unified conversational
retail agent — demoed **live in the GOOPHER extension** on Google Cloud.
**Golden line to repeat:** *"The LLM orchestrates and converses; deterministic code transacts."*

> Pre-flight: warm Cloud Run (`/version`), extension signed in, real object on desk, camera off in Meet, share entire screen, `/dev` + `/skills` tabs open.

---

**1 · Title & context (~45s).** "Thanks for the time. I'm the Applied-AI specialist brought in to unblock this engagement. I'll walk the technical design *and* show a working prototype — GOOPHER — live in this Chrome extension on Google Cloud. I'll speak to the architecture for the domain expert and the business value for the VP, and leave lots of room for questions. Everything is real and deployed — not slideware."

**2 · The challenge / the unblocker (~2m).** "The retailer wants modern self-service for order management and support, over chat *and* voice, for a global base. The blocker isn't 'add a chatbot' — it's four things at once: it must **act** on live inventory/orders, **route** to specialists while keeping context, speak **every channel and modality** in the customer's language, and keep money-moving actions **safe and auditable**. No off-the-shelf box does all four — that's why you engaged a specialist. That solution is GOOPHER."

**3 · Solution at a glance (~90s).** "GOOPHER is a Google ADK multi-agent system on Gemini 2.5 Flash via Vertex AI. It meets all four extension requirements **today** — real sub-agents with shared context, multilingual, multichannel, multimodal including camera 'see-it-shop-it'. And it acts: backend tools hit a mock retail DB for live inventory and order status, and place real orders through a safe gate."

**4 · Architecture (~3m — centerpiece for the technical stakeholder).** "Extension → FastAPI on Cloud Run → a real ADK orchestrator on Gemini 2.5 Flash (Vertex). Before the LLM, deterministic Python does modality/language/channel/memory — fast, free, reliable. The orchestrator delegates to four worker sub-agents via **agent-as-tool**; each picks a registry skill and calls in-process tools against the mock DB in Firestore. Checkout is a **deterministic transactional gate**, and a self-healing Guardian + Cloud Trace + a live `/dev` portal make it observable. Remember: **LLM orchestrates and converses; code transacts.**" *(Open `/dev`.)*

**5 · LIVE DEMO (~8–10m — the hands-on score).** Narrate intent before each click.
- "do you have oreos?" → "place an order of oreo cookies" → **cart + 'please confirm'** → Confirm → staged receipt. *Stress: no substitution; confirm before charge.*
- 📷 Show the **soccer ball** → "what's the price?" → "place an order" → Confirm. *Gemini Vision recognizes + prices + acts.*
- Open **`/dev`** → trace the live pipeline (harness → orchestrator → worker → skill → tool → memory); switch language/voice to show context carried.
- **Finale:** `/dev` Guardian → **💥 Kill Vertex** → DETECT→DIAGNOSE→REMEDIATE→VERIFY → **Restore all**. *If anything is slow (cold start) — narrate as graceful degradation and pivot to the Guardian; it always works.*

**6 · The four hard requirements (~2m).** "Your checklist: sub-agents with shared context (one Firestore session store); multilingual carried across turns; multichannel — web plus a phone simulator, clear path to CCAI; multimodal — text, voice, files, and camera vision. Ask me to go deep on any box."

**7 · Decisions & trade-offs (~3m — technical acumen).** For each: choice → alternative → why. "Deterministic gate (vs LLM placing orders) — safety/auditability. Agent-as-tool (vs transfer) — loops impossible by construction. Deterministic pre-processing (vs LLM agents) — no intelligence needed. Native function-calling + targeted ReAct (vs ReAct everywhere) — reliability. One Gemini model on Vertex — less ops, lower latency. Graceful fallback + self-heal — we degrade, not fail. Push on any row."

**8 · Reliability & trust (~2m).** "An agent touching orders must be trustworthy: never substitutes, always confirms before charging, can't loop, keeps durable shared state, self-heals, fully observable — most of it visible live in `/dev`."

**9 · Business value (~2–3m — for the VP).** "Outcomes: 24/7 self-service across every channel and language; deflection of routine contacts (industry 60–80%); near-zero idle cost (scales to zero); one agent replacing three hand-offs. Growth levers: higher conversion & basket size, instant global reach, lower cost to serve, brand-safe automation. Numbers are illustrative benchmarks — in a pilot we'd instrument the real deflection, conversion, and CSAT."

**10 · Why Google Cloud (~90s — the CE angle).** "Every block is a Google Cloud strength: Gemini on Vertex (one multimodal model, managed security & quota), ADK (multi-agent orchestration + tracing), Cloud Run (serverless, scale-to-zero), Firestore (durable shared state), Cloud Trace (debuggable), and a clear path to CCAI + Vertex Translation. It's native to the cloud, not bolted on."

**11 · Roadmap (~90s).** "Low-risk ramp — the prototype already encodes the hard parts. Pilot: real auth, Secret Manager, hardening, instrumentation. Integrate: live OMS/payments, CCAI telephony, Vertex Translation. Scale: multi-region, evals in CI, more sub-agents. Each phase is integration + hardening, not re-architecture."

**12 · Close + Q&A (~30s, then open).** "To recap: one agent across every channel, language and modality; safe to transact because deterministic code does the transacting; and it heals itself. It directly unblocks the engagement and it's native to Google Cloud. I'd love your questions — I can pull up the extension or `/dev` to answer any of them." *(Keep `QUESTION-ANSWER.md` handy.)*

---

*Full deck: `PRESENTATION.pptx` (speaker notes embedded per slide). Q&A bank: `QUESTION-ANSWER.md`. Deep dive: `ARCHITECTURE.md`.*
