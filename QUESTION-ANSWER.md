# GOOPHER — Question & Answer Bank

A ready-to-use bank of the **most likely questions** about GOOPHER, with crisp
answers. **Part A** is for the **technical team** (architecture, agents, ADK,
reliability, security). **Part B** is for **customer / business stakeholders**
(value, channels, trust, cost). Each answer is a 1–2 sentence spoken version plus
"where to point" so you can prove it live.

> One-sentence pitch: **GOOPHER is a unified, multi-agent conversational retail
> assistant** — text · voice · camera, multi-channel, multi-lingual — built on
> **Google ADK + Gemini 2.5 Flash on Vertex AI**, with a deterministic
> transactional gate, a self-healing Guardian, and a live developer portal.

---

# Part A — Technical team Q&A

## Architecture & agents

**Q: What's the high-level architecture?**
A Chrome MV3 side-panel extension talks over HTTPS+JWT to a FastAPI service on
Cloud Run. The service runs a **Google ADK multi-agent orchestrator** on
**Gemini 2.5 Flash (Vertex AI)**, backed by Firestore. Deterministic
pre-processing (modality/language/channel/memory) wraps the agent run; checkout is
a deterministic transactional gate. *Point at:* `ARCHITECTURE.md §1–2`, `/dev`.

**Q: What agents are there, exactly?**
**5 live ADK `LlmAgent`s** (only in `orchestrator.py`): a ROOT `goopher_orchestrator`
+ 4 workers — `inventory_agent`, `order_agent`, `checkout_agent`,
`order_management_agent`. Plus deterministic Python "agents" (modality/language/
channel), an isolated **Vision** subagent, an isolated **ReAct Advisor**, and the
**Guardian** self-healer. *Point at:* `/skills`, `ARCHITECTURE.md §3`.

**Q: Are these real ReAct agents?**
They run the **ReAct paradigm** (reason → act → observe) but via Gemini's **native
function-calling**, not the text-scratchpad `Thought/Action/Observation` format —
strictly more reliable (no string parsing). The **one** explicit-ReAct agent (ADK
`PlanReActPlanner`) is the read-only Shopping Advisor. *Point at:* `LEARNINGS §3.21`.

**Q: Did you write the agent loop yourself or use the library?**
The agents are stock **`google.adk.agents.LlmAgent`**; ADK's `Runner` provides the
function-calling loop. We only configure each agent (name, model, instruction,
tools) and compose them.

**Q: How does the orchestrator delegate — sub_agents/transfer or agent-as-tool?**
**Agent-as-tool** (`AgentTool`): the orchestrator *calls* a worker like a function,
gets the result back, and stays in control to compose the reply. We deliberately
**do not** use `sub_agents`/`transfer_to_agent` (one reason: it prevents
delegation cycles — see loops below).

**Q: Why are modality/language/channel deterministic Python, not agents?**
They need **no intelligence** (detect language, classify modality, pick channel).
We tried them as ADK agents; they failed ("no text response") for zero benefit.
Deterministic = reliable, free, reproducible. *Point at:* `LEARNINGS §10`.

## State & memory

**Q: How do all agents maintain state?**
One **session-memory store keyed by `session_id`** — durable in **Firestore** in
the cloud, a dict locally — holds turn history + working-memory `facts`; **every**
conversational agent reads/writes it. The ADK harness keeps a parallel ADK session
under the same key. *Point at:* `ARCHITECTURE.md §5j`, the `MEMORY · session updated`
step in `/dev`.

**Q: Is any state per-agent?**
Minimally: `_LAST_VIEWED` (last product, for "order it"), `_last_checkout` (one
turn's cart for the UI), and the Guardian's own health/circuit state. **Vision and
the Advisor are stateless** — they pull memory from tools (e.g. order history).

**Q: How does context survive a channel/language/modality switch?**
The `session_id` is the join key; each `Turn` records its channel/language/modality
and the store is consulted on every turn. Start Web/English, continue Phone/Spanish
— same thread. In the cloud it's Firestore, so it survives autoscaling/scale-to-zero.

## Loop prevention & reliability

**Q: How do you stop agents from looping?**
**Structurally, not by prompting:** (1) **agent-as-tool** — workers return results
and can't transfer control back, so an A→B→A cycle isn't expressible; (2) workers
own **only function tools** (no nested agents) → bounded depth; (3) **single-pass
turn** (mutually-exclusive checkout/adk/fallback); (4) checkout is **deterministic,
outside the loop**; (5) **bounded retries** (1; advisor 2, idempotent); (6) failures
**degrade once** to the deterministic engine; (7) Guardian **circuit breaker** kills
retry storms. *Point at:* `ARCHITECTURE.md §5k`.

**Q: What happens if the LLM/ADK fails mid-turn?**
The turn **falls back once** to a deterministic intent-routing engine that calls
the same tools — so the service degrades to "working without the LLM" rather than
erroring. *Point at:* `ARCHITECTURE.md §5`, `orchestrator._generate_fallback`.

**Q: What's the self-healing Guardian?**
A **separate, isolated** agent wrapping work in a resilience policy — circuit
breaker · retry-with-backoff · failover · self-repair · health probes · chaos
injection · heal-forward. It drives **synthetic** transactions only, so it can't
touch live flows. Demo: `/dev` → 💥 Kill Vertex → watch DETECT→DIAGNOSE→REMEDIATE→
VERIFY → Restore all. *Point at:* `ARCHITECTURE.md §5e`.

## The transactional gate

**Q: Does the LLM place orders / take payment?**
**No.** Checkout is a **deterministic transactional gate** (structured cart →
simulated payment → `ORDER_PLACED` → staged receipt) that runs **before** the LLM
branch, in *every* path (text, voice, camera). The LLM decides *to* check out; it
never *executes* the purchase. "LLM orchestrates, code transacts." *Point at:*
`ARCHITECTURE.md §5b`.

**Q: Two-step confirm — how does that work?**
The gate previews the cart (`confirm=False`) and asks "please confirm"; on confirm
the extension re-sends the **resolved SKU** with `confirm=True` and it places
exactly that item — never a substitute. Works identically for text, voice, and
camera.

**Q: Which agent runs the 9-stage fulfillment pipeline?**
It's the **`order_management_agent`'s** capability (its `fulfillment` skill +
`run_fulfillment` tool), but for a real purchase it runs **deterministically the
moment payment succeeds** (from the checkout gate), not as an LLM step. Ownership ≠
execution. *Point at:* `ARCHITECTURE.md §5i`, the FULFILLMENT card in `/dev`.

## Skills, registry & harness

**Q: Is there a skill registry?**
Yes — `agent_skill_registry.py` registers each skill once (`inventory`, `order`,
`checkout`, `fulfillment`) with metadata + a **`read_only` flag**; agents **pick
skills by name**, and `GET /skills` exposes the live map. The read-only advisor
composes **only read-only skills (asserted in code)** so it can't get a checkout
tool. *Point at:* `ARCHITECTURE.md §5g`.

**Q: What's the "agent harness"?**
A dedicated `harness/` package (`AgentHarness` + `AgentRunResult`) — the **common
scaffolding every agent runs through**: build → session → run-loop → collect →
resilience → structured result. The orchestrator (+4 workers) and the advisor both
use it. *Point at:* `ARCHITECTURE.md §5h`.

## Multimodal — Vision & voice

**Q: How does the camera "see it, shop it" work?**
A separate **Vision subagent** (`POST /vision`) recognizes the item with **Gemini
Vision on Vertex** (`google.genai`, `thinking_budget=0`), resolves it to a real
catalog product (never substitutes), and previews-then-confirms an order through
the same checkout gate. *Point at:* `ARCHITECTURE.md §5c`.

**Q: Why `thinking_budget=0`?**
Gemini 2.5 "thinking" spends output tokens before the visible answer; on short
vision calls and on the ReAct advisor it starved the answer ("plan but no answer").
Disabling thinking + a generous token cap fixes it. *Point at:* `LEARNINGS §3.16, §3.22`.

**Q: How is voice handled in an MV3 side panel?**
Speech-to-text and the camera run in a **popup window** (MV3 side panels can't
reliably get mic/camera); the transcript/frame is relayed back. The mic is kept
**warm** so the first words aren't dropped, and a spoken "confirm order" resolves
the pending checkout.

## LLM models & cost

**Q: Which models, and where?**
**Production = `gemini-2.5-flash` on Vertex AI only** (`LLM_PROVIDER=gemini`,
`USE_VERTEXAI=true`, service-account auth, **no OpenAI key in the cloud**). One
natively-multimodal model does ADK reasoning, multilingual phrasing, **and** vision.
`gpt-4o-mini` is a local-only swappable fallback. *Point at:* `README §🤖 LLM models`.

**Q: What's the per-turn cost / latency profile?**
A turn is ~4–5 LLM calls (orchestrator + worker(s) + phrasing) — accepted for
**visible** multi-agent orchestration (traces + dev portal). Deterministic
pre-processing and checkout add **zero** LLM cost. Could be trimmed by making more
steps deterministic.

## Observability

**Q: How do you debug a multi-agent turn?**
**Cloud Trace** (each agent/tool is a span — a red span pinpoints the failing
node), the **`/dev` developer portal** (live SSE flow: auth → preprocess →
harness → orchestrator → worker → skill → tool → memory), `/metrics`, and a
`/version` build marker. *Point at:* `/dev`, `/version`.

**Q: Why did I see a duplicate card in the portal?**
A cold-start connection reset can make the client re-send; the recorder now
**collapses an identical turn** (same session + message within 90s) onto one card.
*Point at:* `LEARNINGS §3 takeaway 33`.

## Security

**Q: What's the security model?**
**Single-user lockdown:** an email allowlist (`demo@goopher.app`) + a master
password, **fail-closed** (no allowlist match → rejected). JWT bearer tokens;
secrets only in env / GitHub secret (never committed; `.env` gitignored); rate
limiting + request-size limits (DoS). *Point at:* `auth.py`, `middleware.py`.

**Q: Known security deferrals?**
Secret Manager (currently Cloud Run env vars), CORS locked to the extension
origin (currently `*`), network-level IAM, and real identity (Firebase Auth) are
deferred with honest reasons. *Point at:* `LEARNINGS §8`.

## Testing & CI/CD

**Q: How is it tested and shipped?**
**117 unit tests + 8 evals**; push to `main` → GitHub Actions (test+eval) → Cloud
Build → Cloud Run. Because the ADK path isn't exercised in CI, we also run a
**CI-simulation** (block `google.*`, run everything via the deterministic fallback)
to prove the production path is safe across refactors. *Point at:* `tests/`,
`.github/workflows/`, `LEARNINGS §3.25`.

**Q: Isn't the ADK path untested then?**
Its *fallback* and structure are covered; the live ADK path is validated in the
cloud (traces) + the CI-sim of the parallel path. New isolated agents are tested
with **faked runners** (no network) and isolation asserts (e.g. advisor tools
disjoint from checkout).

## Scaling & cloud

**Q: Does it scale / survive scale-to-zero?**
Cloud Run autoscales; **Firestore** session memory is shared + durable across
instances, so `session_id` resolves to the same conversation after scale events.
Rate limiting / dev-portal buffer are per-instance today (fine for single-user).

**Q: Why these tech choices?**
Free-tier-first: Gemini on Vertex ($300 credit), Cloud Run, Firestore. Direct
in-process ADK function tools (MCP-stdio failed in Cloud Run and wasn't justified
for a single consumer). *Point at:* `ARCHITECTURE.md §4`, `LEARNINGS §4`.

---

# Part B — Customer / business stakeholder Q&A

## What it is & the value

**Q: In one sentence, what is GOOPHER?**
A single AI shopping assistant that lets customers **browse, ask, and buy** across
clothing, food, and toys — by **typing, talking, or showing an item to the
camera** — in their own language, on web or phone.

**Q: What problem does it solve?**
It collapses search + support + checkout into one natural conversation, reducing
friction ("do you have BBQ chips?" → "order it") and meeting customers on **any
channel, any language, any input** — no app-switching, no forms.

**Q: What can a customer actually do?**
Find products, check price/stock, get **personalized recommendations**, track
orders, and **place single or bulk orders** with a confirm step — by text, voice,
or camera.

## Channels, languages & modality

**Q: What channels and languages?**
**Web and Phone (voice)** today, with a mobile-device simulator for the phone
channel; **multi-lingual** (e.g. English/Spanish) with the language carried across
the conversation.

**Q: "See it, shop it" — really?**
Yes — point the camera at a real toy or snack, say "what's the price?" or "order
this," and GOOPHER recognizes it, prices it, and (after you confirm) orders it.

## Trust & safety

**Q: Will it ever order the wrong thing or a substitute?**
No. If it can't find the exact item you named/showed, it **says so** rather than
substituting, and every purchase shows a **cart preview and asks you to confirm
before any charge** — by text, voice, or camera alike.

**Q: Can the AI accidentally charge me or place an order on its own?**
No. The AI **never executes payment**. Orders run through a **deterministic,
auditable checkout** that only proceeds after you confirm — the AI just helps you
get there.

**Q: Is my data safe?**
Access is locked to an approved account (allowlist + password, fail-closed),
traffic is authenticated, and secrets are never exposed. (Hardening like Secret
Manager and real SSO is on the roadmap.)

## Reliability

**Q: What if the AI service has a hiccup?**
It **degrades gracefully** — a deterministic backup answers and the order flow
still works without the AI. We also built a **self-healing Guardian** that detects
a failure, diagnoses it, fixes/fails-over to keep you served, and restores itself —
all visible live.

**Q: Is it reliable enough for production?**
It's production-shaped: containerized, auto-deployed (CI/CD), observable (live
traces + portal), tested (117 tests), and self-healing — with an honest list of
remaining hardening items.

## Cost & deployment

**Q: What does it cost to run?**
Built **free-tier-first** on Google Cloud (Gemini via Vertex credit, Cloud Run,
Firestore). It scales to zero when idle, so idle cost is near-nothing.

**Q: How is it deployed / updated?**
Every change pushed to `main` is automatically tested and deployed to Cloud Run;
a `/version` marker confirms exactly which build is live.

## Roadmap & limitations

**Q: What's intentionally not done yet?**
Real identity (SSO), Secret Manager, tighter CORS/network lockdown, multi-user
support, and live payment integration — all deferred deliberately for the
single-user demo, with reasons documented.

**Q: What would the next milestones be?**
Multi-user + real auth, real payment/inventory integrations, Secret Manager +
network hardening, and optionally a visible "watch it reason" mode and dynamic
skill selection.

---

## Quick-reference cheat sheet (for live demos)

| Prove it | Where |
|---|---|
| Multi-agent pipeline (agent → harness → skill → tools) | `/dev` (any chat turn) |
| Skill registry / capabilities | `GET /skills` |
| Which build is live | `GET /version` |
| Self-healing | `/dev` → 💥 Kill Vertex → Restore all |
| Durable memory | `/dev` → `MEMORY · session updated` step |
| Confirm-before-charge | order by text/voice/camera → "please confirm" |
| Two agent styles | tap 🧠 (ReAct advisor) vs normal chat (function-calling) |
| Vision | 📷 → show an item → ask/"order" |

*See **DEMO.md** for the full CTO walkthrough script, **ARCHITECTURE.md** for the
deep dive, and **LEARNINGS.md** for the engineering story.*
