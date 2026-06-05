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

**4 · Architecture — overview (~2m).** "Extension → FastAPI on Cloud Run → a real ADK orchestrator on Gemini 2.5 Flash (Vertex). Before the LLM, deterministic Python does modality/language/channel/memory — fast, free, reliable. The orchestrator delegates to four worker sub-agents via **agent-as-tool**; each picks a registry skill and calls in-process tools against the mock DB in Firestore. Checkout is a **deterministic transactional gate**, and a self-healing Guardian + Cloud Trace + a live `/dev` portal make it observable. Remember: **LLM orchestrates and converses; code transacts.**" *(Open `/dev`.)*

**5 · Architecture deep-dive — trace one turn (~3–4m; great for Q&A).** "Walk the numbers 1→9: input from the extension over HTTPS+JWT; Cloud Run + FastAPI auth & limits; deterministic pre-process (modality/language/channel) that LOADS memory by session_id; a branch where a purchase goes to the deterministic gate and skips the LLM; the Agent Harness (build → ADK session → run, with retries/degrade-once); the ROOT orchestrator on Gemini/Vertex selecting ONE worker via agent-as-tool; the worker picking a registry skill and calling tools via native function-calling; tools reading/writing the mock retail DB in Firestore (catalog/orders/ORDER_PLACED); and finally channel-format → PERSIST memory → stream back → trace to Cloud Trace + /dev. Cross-cutting on every turn: the deterministic gate, the isolated side-agents (vision/advisor/guardian), and observability + resilience. I can drill into any box."

**6 · Inside the platform — components in detail (~3–4m; the rigor slide).** "Six concerns, each its own panel. SUB-AGENTS are the LLM agents — the ROOT goopher_orchestrator and four named workers (inventory_agent, order_agent, checkout_agent, order_management_agent) plus three isolated ones (vision_agent, advisor_agent, guardian). AGENT SKILLS are a SEPARATE layer: a skill is an instruction + tools, registered once; an agent PICKS a skill — browse/track are read-only, checkout/fulfillment are transactional, and the read-only flag is enforced in code (see GET /skills). AUTHENTICATION: JWT on every call, email allowlist + master password, fail-closed, rate/size limits, CORS. MEMORY AGENT: one session store keyed by session_id, durable in Firestore, loaded at start and persisted at end of each turn. GUARDRAILS: deterministic gate, no-substitution, confirm-before-charge, loop prevention, graceful fallback, self-healing Guardian. QUALITY: 117 unit tests + 8 evals gate every change via CI/CD, plus a CI-sim that blocks the google packages to prove the production fallback. Headline: sub-agents and skills are different layers, and safety/quality are first-class."

**7 · LIVE DEMO (~8–10m — the hands-on score).** Narrate intent before each click.
- "do you have oreos?" → "place an order of oreo cookies" → **cart + 'please confirm'** → Confirm → staged receipt. *Stress: no substitution; confirm before charge.*
- 📷 Show the **soccer ball** → "what's the price?" → "place an order" → Confirm. *Gemini Vision recognizes + prices + acts.*
- Open **`/dev`** → trace the live pipeline (harness → orchestrator → worker → skill → tool → memory); switch language/voice to show context carried.
- **Finale:** `/dev` Guardian → **💥 Kill Vertex** → DETECT→DIAGNOSE→REMEDIATE→VERIFY → **Restore all**. *If anything is slow (cold start) — narrate as graceful degradation and pivot to the Guardian; it always works.*

**8 · The four hard requirements (~2m).** "Your checklist: sub-agents with shared context (one Firestore session store); multilingual carried across turns; multichannel — web plus a phone simulator, clear path to CCAI; multimodal — text, voice, files, and camera vision. Ask me to go deep on any box."

**9 · Decisions & trade-offs (~3m — technical acumen).** For each: choice → alternative → why. "Deterministic gate (vs LLM placing orders) — safety/auditability. Agent-as-tool (vs transfer) — loops impossible by construction. Deterministic pre-processing (vs LLM agents) — no intelligence needed. Native function-calling + targeted ReAct (vs ReAct everywhere) — reliability. One Gemini model on Vertex — less ops, lower latency. Graceful fallback + self-heal — we degrade, not fail. Push on any row."

**10 · Engineering challenges (~2-3m — hands-on depth). "Building this surfaced real problems: ADK let the model skip sub-agents and a SequentialAgent can't be an AgentTool, so I moved pre-processing to deterministic code and used agent-as-tool. Gemini 2.5's thinking starved the answer on vision and the ReAct advisor — fixed with thinking_budget=0 plus a grounded synthesis fallback. The ADK path isn't testable in CI, so I added a CI-sim that blocks the google packages and runs the prod fallback. No-substitution + a deterministic confirm-before-charge gate keep the LLM out of payments; context lives in one Firestore session store; and the SDK/quota gotchas — google.genai for Vertex, pin the right model. All written up in LEARNINGS.md."

**11 · Wow factor (~90s — the memorable beat). "Six things to remember: show a product to a camera and it orders it; break a dependency on stage and watch it self-heal; see the live agent pipeline for every turn; two agent styles on one model; the AI never touches payment; and it's production-shaped — tested, CI/CD, self-healing — on Google Cloud. Most demos show one of these; GOOPHER shows all six, live."

**12 · Reliability & trust (~2m).** "An agent touching orders must be trustworthy: never substitutes, always confirms before charging, can't loop, keeps durable shared state, self-heals, fully observable — most of it visible live in `/dev`."

**13 · Recursive self-improvement / RSI (~2m — the it-gets-better wow). "Most agents are static. GOOPHER self-heals on TWO levels: the Guardian heals the infrastructure; the CriticAgent heals the BEHAVIOUR. When an answer is poor, the shopper thumbs-down; the CriticAgent uses Gemini-as-judge to find the root cause and write a corrective lesson, stores it confidence-gated, and retrieves it via RAG to improve the next similar answer — no retraining, no redeploy. Live: in /dev click Reset lessons, ask 'do you have laptops?' (flat), thumbs-down, ask again — now it names real in-stock alternatives and asks a clarifying question, and /dev shows DETECT -> JUDGE -> LESSON. In production: a Cloud Run Job every 15 min from CCAI Insights, backed by Vertex AI Vector Search. Isolated and additive — never changes routing or checkout."

**14 · Business value (~2–3m — for the VP).** "Outcomes: 24/7 self-service across every channel and language; deflection of routine contacts (industry 60–80%); near-zero idle cost (scales to zero); one agent replacing three hand-offs. Growth levers: higher conversion & basket size, instant global reach, lower cost to serve, brand-safe automation. Numbers are illustrative benchmarks — in a pilot we'd instrument the real deflection, conversion, and CSAT."

**15 · Why Google Cloud (~90s — the CE angle).** "Every block is a Google Cloud strength: Gemini on Vertex (one multimodal model, managed security & quota), ADK (multi-agent orchestration + tracing), Cloud Run (serverless, scale-to-zero), Firestore (durable shared state), Cloud Trace (debuggable), and a clear path to CCAI + Vertex Translation. It's native to the cloud, not bolted on."

**16 · Key learnings (~90s — reflection / seniority). "Six takeaways: ReAct is a paradigm not a class (native function-calling is ReAct done better); LLM orchestrates, code transacts; loop safety is graph shape not prompts; a model quirk that bit once bites again (encode the fix); test the path production actually runs (CI-sim of the ADK fallback); and centralize state by session_id while keeping agents stateless. Detailed in LEARNINGS.md."

**17 · Roadmap (~90s).** "Low-risk ramp — the prototype already encodes the hard parts. Pilot: real auth, Secret Manager, hardening, instrumentation. Integrate: live OMS/payments, CCAI telephony, Vertex Translation. Scale: multi-region, evals in CI, more sub-agents. Each phase is integration + hardening, not re-architecture."

**18 · Close + Q&A (~30s, then open).** "To recap: one agent across every channel, language and modality; safe to transact because deterministic code does the transacting; and it heals itself. It directly unblocks the engagement and it's native to Google Cloud. I'd love your questions — I can pull up the extension or `/dev` to answer any of them." *(Keep `QUESTION-ANSWER.md` handy.)*

---

*Full deck: `PRESENTATION.pptx` (speaker notes embedded per slide). Q&A bank: `QUESTION-ANSWER.md`. Deep dive: `ARCHITECTURE.md`.*
