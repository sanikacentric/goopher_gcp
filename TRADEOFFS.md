# GOOPHER — Trade-offs & Design Decisions

Every meaningful trade-off made building GOOPHER, with the **options considered**,
what was **chosen**, and the **why / cost accepted**. Grouped by area. For the
narrative behind many of these, see [`LEARNINGS.md`](LEARNINGS.md); for the
architecture, [`ARCHITECTURE.md`](ARCHITECTURE.md).

> **Five principles that drive most of these choices**
> 1. **LLM orchestrates and converses; deterministic code transacts.** Anything that
>    moves money/inventory or needs no intelligence is plain code.
> 2. **Match the tool to the task** — native function-calling for tool-use, explicit
>    ReAct only where a visible plan adds value, LLM-as-judge for single-shot
>    evaluation, deterministic code for classification/routing.
> 3. **Isolate new capabilities** — vision, advisor, guardian, critic are separate
>    agents that can't break the working flows.
> 4. **Degrade, don't fail** — every risky path has a graceful fallback.
> 5. **Free-tier-first** — accept some latency/limits to run at ~$0 idle.

---

## A. Agent architecture & orchestration

| Decision | Options considered | Chosen | Why / cost accepted |
|---|---|---|---|
| **Multi-agent composition** | ADK `sub_agents` + `transfer_to_agent` vs **agent-as-tool** (`AgentTool`) | **Agent-as-tool** | Orchestrator *calls* a worker and stays in control to compose the reply; workers **can't transfer control back**, so A→B→A delegation loops are **not expressible**. Cost: orchestrator must aggregate results itself. |
| **Pre-processing (modality / language / channel / memory)** | ADK `LlmAgent`s vs **deterministic Python** | **Deterministic Python** | These need *no intelligence*; tried them as ADK agents and they failed ("no text response") for zero benefit. Plain code is reliable, free, reproducible. Cost: less "everything is an agent" purity. |
| **Worker capabilities** | Workers own nested agents vs **only function tools** | **Function tools only** | Bounds the graph depth (`orchestrator → one worker → tools → return`); no worker→worker recursion. |
| **Reasoning style (production agents)** | Text-scratchpad ReAct vs **native function-calling** | **Native function-calling** | The ReAct paradigm via Gemini's structured tool-calling — no brittle `Thought/Action` parsing (which caused "no text response"). Cost: less visible "thinking" on the main path. |
| **Planner** | `PlanReActPlanner` everywhere · `BuiltInPlanner` · **none on production, ReAct only for the advisor** | **None on production; `PlanReActPlanner` for the read-only advisor only** | Our task graph is shallow (one worker, one/two tools) — a planner adds latency, tokens, and parsing fragility. The advisor is the one place a *visible* plan adds value. |
| **Sub-agent execution** | Run ADK agents *and* deterministic vs **one path** | **ADK when on, deterministic backup only** | Eliminates double work + duplicate traces. |
| **Shared scaffolding** | Inline run-loop per agent vs **common `AgentHarness`** | **Common harness** | One tested, observable build→session→run→collect→resilience path for every ADK agent instead of copies. |
| **Skill wiring** | Import skill modules per agent vs **`agent_skill_registry`** | **Registry (pick by name)** | Single source of truth + `read_only` flag (enforced for the advisor) + `/skills` introspection. Behaviour unchanged. |

## B. LLM, model & SDK

| Decision | Options considered | Chosen | Why / cost accepted |
|---|---|---|---|
| **LLM provider** | Gemini (Vertex) vs OpenAI | **Both, switchable (`LLM_PROVIDER`)** | Gemini for the $300 Vertex credit + ADK; OpenAI a no-quota local fallback. Kept Gemini paths even on OpenAI. |
| **Model** | `gemini-2.0-flash` vs **`gemini-2.5-flash`** | **2.5-flash** | 2.0-flash returns `limit: 0` on this account; 2.5-flash is the one with quota and is natively multimodal (reasoning + vision in one model). |
| **SDK** | legacy `google.generativeai` vs **unified `google.genai`** | **`google.genai` (`vertexai=True`)** | The legacy SDK **cannot reach Vertex** — production runs Vertex with no API key, so the unified client is required. |
| **"Thinking" budget** | default thinking vs **`thinking_budget=0`** (short structured calls) | **0 for vision / advisor / critic-judge** | 2.5-flash thinking spends the output budget *before* the answer → empty text on short calls; disabling it fixes the "plan/answer but no text" stalls. Cost: no chain-of-thought on those calls (not needed). |
| **Tool transport** | MCP vs **direct in-process ADK function tools** | **Direct** | MCP-stdio failed in Cloud Run; a single in-process consumer doesn't justify the indirection. |
| **Cost vs visibility** | Fewer LLM calls vs **visible multi-agent orchestration** | **Visible orchestration** | The deliverable goal was *demonstrable* agent orchestration (Cloud Trace + `/dev`). Accepted **~4–5 LLM calls/turn** for that. |
| **Dependency pinning** | exact pins vs **ranges (`>=`)** | **Ranges** | Exact pins caused a hard `mcp` / `google-adk` resolution conflict. |

## C. Transactions, trust & guardrails

| Decision | Options considered | Chosen | Why / cost accepted |
|---|---|---|---|
| **Who places orders** | LLM executes checkout end-to-end vs **deterministic transactional gate** | **Deterministic gate** | "LLM orchestrates, code transacts." Structured cart → simulated payment → `ORDER_PLACED` → receipt is auditable, reproducible, and never a hallucinated purchase. The LLM decides *to* check out, not *how*. |
| **Fulfillment (9-stage)** | LLM-run vs **deterministic, post-payment** | **Deterministic, triggered by the gate** | Owned by `order_management_agent` (the `fulfillment` skill), but executed as code the moment payment succeeds — reliable, never skipped. |
| **Out-of-stock / unknown item** | Substitute a similar product vs **refuse + offer alternatives** | **Never substitute** | A retail agent that swaps the wrong product is a trust failure. It says it doesn't carry it (and, post-RSI, suggests in-stock alternatives). |
| **Charge timing** | Place immediately vs **preview + "please confirm"** | **Confirm-before-charge on EVERY modality** (text, voice, camera) | No surprise charges; the same gate handles all input paths. Cost: one extra step. |
| **Loop prevention** | Prompt the model not to loop vs **structural** | **Structural** (agent-as-tool, no nested agents, single-pass turn, bounded retries, circuit breaker) | Loop safety is a property of the graph shape, not prompt wording. |
| **Retries** | Unbounded / exponential vs **bounded** | **`retries=1` default; `2` for the read-only advisor only** | No retry storms; only idempotent (read-only) work retries. |

## D. State, memory & data

| Decision | Options considered | Chosen | Why / cost accepted |
|---|---|---|---|
| **Conversation memory** | in-process dict vs **Firestore** | **Firestore in cloud, dict locally** | A dict loses context across Cloud Run instances / scale-to-zero; Firestore is durable + shared by `session_id`. |
| **State ownership** | per-agent state vs **one session store** | **Centralized by `session_id`** | Context survives channel/language/modality switches; fewer stateful components to drift. Vision & advisor are stateless (pull memory from tools). |
| **Database** | SQLite only vs Firestore only vs **both** | **SQLite local (seed on boot), Firestore cloud (persistent + auto-sync catalog)** | Local stays hermetic/offline; cloud persists orders and auto-resyncs the catalog on deploy without a manual seed. |
| **Catalog re-seed** | manual seed vs **auto-sync if changed** | **Auto-sync** | Deploys don't require a manual reseed; runtime orders/customers are preserved. |
| **Contextual ordering ("order it")** | re-ask the user vs **track last-viewed + resolve from memory** | **Track last-viewed** | "ask about X → order it" works; quantity is stripped from the product name so "10" never matches "10-Pack". |

## E. Self-healing & self-improvement

| Decision | Options considered | Chosen | Why / cost accepted |
|---|---|---|---|
| **Guardian (infra self-heal)** | wrap real flows vs **isolated synthetic transactions** | **Isolated synthetic** | It must *never* be able to break the working/demo flows; the same `protect()` API could wrap real ops behind a flag later. |
| **Self-heal visibility** | recovery code only vs **live chaos buttons + staged HEAL card** | **Visible** | Self-healing is only a "wow" if you can watch DETECT→DIAGNOSE→REMEDIATE→VERIFY live. |
| **RSI CriticAgent — agent type** | ADK `LlmAgent` / ReAct vs **LLM-as-judge (direct `google.genai`)** | **LLM-as-judge** | Judging a failure is a single structured evaluation (conversation → JSON verdict) — no multi-step tool loop, so ADK/ReAct would add cost/fragility for nothing. |
| **RSI storage / retrieval** | Vertex AI Embeddings + Vector Search (+ AlloyDB) vs **Firestore + keyword-RAG** | **Firestore + keyword-RAG (prototype)** | The vector stack isn't available to run here; kept the *shape*, documented Embeddings + Vector Search + Cloud Run Job/Scheduler as the production path. |
| **RSI failure source** | CCAI Insights low-CSAT vs **extension 👎 flag** | **👎 flag (demoable now)** | Works live in the extension; CCAI Insights is the production source. |
| **RSI lesson application** | wire RAG into `/chat` vs **keep fully isolated** | **Additive, guarded injection** | Honors "don't touch existing logic": it only *appends* guidance on the LLM paths, is a **strict no-op when no lesson matches**, and never changes routing/checkout. Without injection, "learned" ≠ "applied". |
| **RSI concreteness** | offer categories vs **inject real in-stock items** | **Real in-stock items** | The lesson alone gave vague answers; injecting a few real products makes the improved answer concrete (names products + asks a question). |
| **Lesson persistence vs demo** | always-on persistence vs **+ a reset control** | **Persist + `/dev` Reset** | Lessons should stick (production), but a repeatable before→teach→after demo needs a reset. |

## F. Reliability, testing & ops

| Decision | Options considered | Chosen | Why / cost accepted |
|---|---|---|---|
| **Failure behaviour** | LLM-only vs **deterministic fallback engine** | **Fallback** | The service stays useful (grounded answers) during an LLM outage/quota; also keeps tests hermetic & offline. |
| **Testing the prod path** | trust local green tests vs **CI-sim** | **CI-sim** (block `google.*`, run everything via the fallback) | The ADK path isn't exercisable in CI (no creds); the CI-sim proves the production path is safe across refactors. |
| **New isolated agents in tests** | live calls vs **faked runners + isolation asserts** | **Faked + asserts** | Hermetic; e.g. assert the advisor's tools are disjoint from checkout. |
| **Dev portal duplicate turns** | show every record vs **collapse cold-start resends** | **Collapse identical turns in a window** | A cold-start connection reset re-sent the same turn; merge them so one ask = one card (narrowly, so real re-asks still show). |
| **Scaling** | min-instances (warm) vs **scale-to-zero** | **Scale-to-zero** | Near-$0 idle cost; accept occasional cold-start latency (and the resend it can cause, handled above). `min-instances: 1` is a one-flag upgrade for the demo. |
| **`/version` marker** | infer from logs vs **explicit build marker** | **`/version`** | Ends "is it even deployed?" guessing in one HTTP call. |
| **Build marker discipline** | none vs **bump every deploy** | **Bump + poll until live** | Confirms exactly which code Cloud Run is running before testing. |
| **Order-email transport** | **Gmail SMTP** vs **Resend** (free API) vs no email | **Resend** (with an SMTP fallback path) | Gmail SMTP needs a per-account **App Password + 2FA**, ties the service to a personal mailbox, and means **opening an SMTP egress path from Cloud Run** (port 587/465) — extra config and a spam-reputation risk. Resend is a clean free tier: a single **stdlib HTTPS POST** (no SDK), an API key injected like any other secret, and no SMTP handshake. SMTP is still supported via env vars for anyone who prefers it. **Cost accepted:** the no-domain Resend test sender (`onboarding@resend.dev`) only delivers to the account owner's address until a domain is verified — fine for the single-recipient demo. |
| **Email vs the order** | in the checkout path vs **best-effort side-effect** | **Side-effect, `try/except`, after placement** | A mail-provider outage must **never** fail a paid order. The order is committed first; the email returns `{sent, mode}` and any error is swallowed + logged. |
| **No-secret default** | require creds vs **simulated mode** | **Simulated by default** | The feature is demoable & testable offline (logs + a `📧 simulated` line); flip to real delivery by setting one env var — no code change. |
| **Excel/CSV bulk parsing** | decode-as-text vs **format-aware parser** | **openpyxl/csv, branch on bytes** | An `.xlsx` is a binary ZIP; decoding it as UTF-8 produced garbage and silently fell back to a default basket. Parse by the real format; resolve **by SKU first, then name** (never substitute). |

## G. Security (intentionally deferred for the single-user demo)

| Decision | Options considered | Chosen (now) | Production upgrade |
|---|---|---|---|
| **Access control** | open vs **allowlist + master password, fail-closed** vs SSO | **Allowlist + master pw, fail-closed** | Real identity (Firebase Auth / IdP) |
| **Secrets** | committed vs env var vs Secret Manager | **Env var / GitHub secret (never committed)** | Secret Manager |
| **CORS** | locked origin vs `*` | **`*`** (extension convenience) | Lock to the extension origin |
| **Network** | public vs IAM-locked | **Public Cloud Run** | Network-level IAM lockdown |
| **Rate limiting** | Redis/Firestore-backed vs **in-process sliding window** | **In-process** | Shared store under autoscaling |
| **Dev portal** | auth'd vs open (`DEV_PORTAL_ENABLED`) | **Open, flag-gated** | Auth or disable in prod |

*(All deferrals are honest and documented — see `LEARNINGS.md §8`.)*

## H. Presentation & tooling (minor)

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| **Deck generation** | hand-built slides vs **pptxgenjs (code)** | **pptxgenjs** | Reproducible, version-controlled, scriptable QA (geometry lint). |
| **Animations** | none (pptxgenjs has no API) vs **OOXML post-process** | **Post-process** | Inject fade transitions + per-card build animations directly into the `.pptx` XML. |
| **Slide rendering / visual QA** | LibreOffice/poppler vs **PowerPoint COM** | **PowerPoint COM** | LibreOffice/poppler aren't installed on the machine; PowerPoint renders the real file for fresh-eyes QA. |

---

## The trade-offs that define GOOPHER (the short list)

1. **Deterministic gate over LLM-executed checkout** — safety & auditability over flexibility.
2. **Agent-as-tool over transfer** — loop-proof orchestration over hands-off delegation.
3. **Deterministic pre-processing over "everything is an agent"** — reliability/cost over purity.
4. **Native function-calling over ReAct (except the advisor)** — robustness over visible reasoning.
5. **LLM-as-judge over an ADK/ReAct critic** — right tool for a single-shot evaluation.
6. **Isolated new agents (vision/advisor/guardian/critic)** — never risk the working flows.
7. **Additive, no-op-by-default RSI injection** — improve answers without changing existing logic.
8. **Firestore session state over per-instance memory** — durable, shared context.
9. **Graceful fallback + CI-sim over trusting the happy path** — degrade, don't fail; test what prod runs.
10. **Free-tier scale-to-zero over warm instances** — ~$0 idle, accept cold-start latency.

*See also: `ARCHITECTURE.md` (§5a–§5l), `LEARNINGS.md` (§4 + the §3.x war stories), and `DEMO.md` (§5d–§5g) for where these show up live.*
