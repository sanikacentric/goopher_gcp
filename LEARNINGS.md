# GOOPHER — Build Retrospective & Learnings

> A detailed, honest record of building **GOOPHER** — a unified conversational
> retail agent (Chrome extension + ADK/Gemini backend on Google Cloud) — from an
> empty directory to a deployed, CI/CD-driven, single-user-locked service with a
> live developer portal. This captures the **failures, trade-offs, challenges,
> decisions, and how each was resolved**, grounded in the actual commit history
> (50 commits).

**Date:** 2026-05-31 → 2026-06-01
**Repo:** https://github.com/sanikacentric/goopher_gcp
**Live service:** https://goopher-api-7vnucwimtq-uc.a.run.app
**GCP project:** `sanika-project-2107` (Free Trial, $300 credit)

---

## 1. What we set out to build

A production-style, multi-department conversational retail agent:

- **Frontend:** Chrome MV3 extension ("GOOPHER") side panel + a "Marketplace"
  storefront landing page.
- **Backend:** FastAPI on Cloud Run, with a **Google ADK** orchestrator
  coordinating sub-agents (modality, language, channel) + inventory/order tools.
- **LLM:** Gemini (via AI Studio, then Vertex AI) — later toggled with OpenAI.
- **Data:** mock catalog (women's casual clothing + food/snacks) in
  SQLite (local) / Firestore (cloud).
- **Cross-cutting:** auth, memory, observability (Cloud Trace), evals, tests,
  Docker, CI/CD, abuse protection, and a developer portal.

---

## 2. Timeline of phases

| Phase | Commits | Theme |
|------|---------|-------|
| 1. Scaffold | `36d518b`–`e5a53f4` | Full project skeleton, mock data, tests, evals, Docker, CI stub |
| 2. Search & data realism | `a172aa1`–`b2e19e3` | Fix search, add page-visible products, two departments |
| 3. Storefront & branding | `956b072`–`a9d2228` | Marketplace landing page, naming |
| 4. Extension UX & voice | `25d7eb2`, `fa9827c`–`269db26` | Login flow, mic, voice output |
| 5. LLM provider wrangling | `bd69778`–`ba32dc4` | Gemini model/quota, OpenAI switch, thinking-token bug |
| 6. Cloud + ADK + MCP | `749dcfb`–`9fc14a3` | Vertex AI, real ADK agent-tools, MCP experiment |
| 7. CI/CD (the long haul) | `75e1ac4`–`1f598da` | GitHub Actions deploy — many real failures |
| 8. Architecture cleanup | `49573fd` | Remove MCP, use direct ADK function tools |
| 9. Production hardening | `6991dca`–`1174d83` | Single-user lockdown, Firestore memory, rate limiting |
| 10. Developer portal | `c91b489`–`d4b24c6` | Live end-to-end flow visualizer |

---

## 3. Failures, root causes, and fixes (the meat)

This section is the real value: every non-trivial thing that broke, **why**, and
**how** it was fixed.

### 3.1 Pydantic class-level field-default mutation (subtle, high-impact)
- **Symptom:** A flaky test — `test_language_is_detected_and_persisted` saw
  `'en'` instead of `'es'`, but **only when run after `test_api.py`**.
- **Root cause:** A dead no-op block in the `/chat` handler:
  `if req.language is None: req.language = None`. Assigning to the *instance*
  attribute mutated the **class-level** `ChatRequest.model_fields['language'].default`
  from `None` to `'en'`, poisoning every later request built with the default.
- **Fix:** Deleted the useless block.
- **How we found it:** A `__setattr__` watchpoint — subclassed the FieldInfo's
  type and printed a stack trace whenever `default` was set to `'en'`.
- **Lesson:** Avoid pointless assignments to Pydantic model instance attributes
  in handlers; they can have surprising class-level side effects.

### 3.2 Keyword search returned the whole catalog (or nothing)
- **Symptom 1:** "jessica simpson … dress can let me know the price" → *no
  results* (whole sentence matched as one literal substring).
- **Symptom 2:** "what is the price of cheese **snack** crackers" → returned
  **all 5 snacks** (the category word "snack" matched every food item).
- **Root causes:** (a) substring match on the entire query string; (b) generic
  category words counted as keywords; (c) colors/sizes weren't in the search text.
- **Fixes (across `a172aa1`, `0f693c1`, `bdb5d1d`):**
  - Tokenize the query, drop stopwords + generic category words.
  - Include colors/flavors + sizes in the searchable text.
  - Naive plural→singular (`oreos`→`oreo`).
  - **Weight** name/brand/flavor hits 3× description hits, then keep only results
    scoring ≥ 60% of the top — so a specific ask returns the named product, not
    every weak match.
  - Map a bare department word ("snacks", "dresses") to a department filter.
- **Lesson:** Free-text retrieval needs tokenization + relevance ranking, not
  substring matching; and "category words" are noise, not signal.

### 3.3 Language mis-detection (English flagged as French)
- **Symptom:** Footer showed `web · fr` for an English query.
- **Root cause:** Substring matching — `"je"` matched inside "**Je**ssica",
  `"o"`/`"wo"` matched ordinary English.
- **Fix:** Whole-word matching + Unicode-script shortcuts (Devanagari→hi,
  CJK→zh); require ≥2 word hits (or 1 accented word) to switch off English.
- **Lesson:** Heuristic language ID must match whole tokens, not substrings.

### 3.4 Gemini model quota — `limit: 0` vs daily exhaustion
- **Symptom:** Replies were robotic templates, not natural language.
- **Root cause 1:** `gemini-2.0-flash` returned `429 limit: 0` — the user's
  AI Studio project grants **zero** quota for that specific model.
- **Fix:** Switched to `gemini-2.5-flash`, which works on the same key (`bd69778`).
- **Root cause 2 (later):** Free tier = **20 requests/day**; heavy testing
  exhausted it.
- **Fix:** Vertex AI (the $300 credit) lifts the quota wall entirely.
- **Lesson:** "Quota exceeded" has two flavors — `limit: 0` (model not entitled
  → change model) vs daily cap (wait / change tier). Read the error detail.

### 3.5 Gemini 2.5 "thinking" ate the whole token budget
- **Symptom:** HTTP 200 but **empty** replies → fell back to template.
- **Root cause:** gemini-2.5-* use "thinking" by default, consuming output
  tokens internally; the response finished as `MAX_TOKENS` with no visible text,
  and `resp.text` raised.
- **Fix (`eca7a4f`):** `max_output_tokens=2048` to leave budget for the answer,
  and a safe `_extract_text()` that concatenates text parts (never `resp.text`,
  which throws on non-text parts).
- **Lesson:** Reasoning models silently spend output budget on thinking — size
  `max_output_tokens` accordingly, and parse responses defensively.

### 3.6 The agent refused valid items ("I don't sell Oreos")
- **Symptom:** Gemini refused food even though the tool returned it.
- **Root cause:** `ROOT_INSTRUCTION` still said "JCPenney casual dresses only."
- **Trap we hit:** The first fix's `Edit` **silently failed** (wrong dash in the
  match string), and we committed claiming it was fixed (`b869ee3`) — it wasn't.
  Caught it via live testing; the real fix landed in `7af25e7`.
- **Fix:** Rewrote the system prompt for two departments + "trust tool results,
  never claim you only sell one category."
- **Lesson:** **Verify edits actually applied** before claiming success — and
  test behavior live, not just "the code looks right." An honest miss.

### 3.7 Chrome MV3 microphone — `not-allowed`
- **Symptom:** Clicking the mic → `Voice error: not-allowed`.
- **Root cause:** MV3 **side panels cannot reliably obtain mic permission** —
  `SpeechRecognition.start()` throws even when the mic is allowed in Chrome.
- **First attempt (`269db26`):** request `getUserMedia` before recognition —
  helped but still unreliable in the side panel.
- **Real fix (`fa9827c`):** Move voice capture to a **popup window** (a normal
  extension page *can* get the mic), which captures speech and relays the
  transcript back to the side panel via `chrome.runtime` messaging.
- **Lesson:** Side panels are sandboxed differently from extension windows;
  mic/permission-heavy work belongs in a popup.

### 3.8 Voice double-answers + speaking when not wanted
- **Symptoms:** Typed questions were spoken aloud; voice questions answered twice.
- **Root causes:** Spoke on every reply (toggle on); the recognizer emitted
  multiple final results → sent twice.
- **Fixes (`ec04468`, `2064873`):** Speak only for mic-originated questions
  (a `viaVoice` flag); one-shot guard + unique message id to de-dup transcripts.

### 3.9 The CI/CD saga (8+ distinct failures — the hardest part)
Getting GitHub Actions → Cloud Run working surfaced a *chain* of real,
independent issues. Each is a useful lesson on its own:

1. **`SHORT_SHA` empty** on manual `gcloud builds submit` → image tag ended in a
   bare `:`. **Fix:** use `$BUILD_ID` (`28bde8d`).
2. **Dependency conflict:** pinned `mcp==1.2.0` but `google-adk` needs
   `mcp>=1.8`. **Fix:** version ranges, not exact pins (`3ebb196`).
3. **Cloud Shell ≠ local files:** Cloud Shell is a fresh VM — `cloudbuild.yaml`
   wasn't there until we pushed to GitHub and cloned.
4. **Firestore seed `PERMISSION_DENIED` / import error:** Cloud Shell's system
   Python clashed; solved with a clean venv + `roles/datastore.user` grant.
5. **Cloud Run `401 Unauthorized`:** `--allow-unauthenticated` blocked; needed an
   explicit `allUsers` `run.invoker` binding.
6. **Gate skipped deploy ("secrets not set"):** inlining the multi-line
   `GCP_SA_KEY` JSON into a bash `if` **broke the test** (newlines). **Fix:**
   pass secrets via `env:` and test the env var (`510cf00`).
7. **Build log-streaming exit 1:** the deployer SA couldn't stream the default
   bucket's logs. `--suppress-logs` didn't help on that gcloud version; **real
   fix:** grant the SA `roles/viewer` (`08c3b92`).
8. **`--set-env-vars` "Bad syntax for dict arg":** a secret value contained the
   SA-key JSON (colons + newlines), breaking the comma-separated dict parser.
   Tried `--env-vars-file` (then hit YAML indentation from the heredoc inside the
   `run: |` block), then finally **re-set the corrupted secrets cleanly** and
   dropped unnecessary keys (`6da895c`, `1f598da`).
- **Net lesson:** CI/CD against a real cloud is a *sequence* of small, distinct
  failures (image tags, deps, perms, secret encoding, log streaming, arg
  parsing). Read each error literally, fix one layer at a time, and prefer
  structural fixes (ranges, env-files, IAM roles) over band-aids.

### 3.10 Docker image missing the storefront
- **Symptom:** `/` returned `{"detail":"Not Found"}` in the cloud.
- **Root cause:** Dockerfile copied `backend/` and `scripts/` but **not `site/`**,
  so the static mount's `is_dir()` check failed in the container.
- **Fix (`75502d5`):** `COPY site/ ./site/`.
- **Lesson:** "Works locally" ≠ "shipped" — the image must contain every runtime
  asset; verify with the deployed artifact, not the local tree.

### 3.11 MCP-over-stdio failed inside Cloud Run
- **What we tried:** Real Model Context Protocol — launch the MCP server as a
  stdio subprocess and connect via ADK's `MCPToolset` (`9fc14a3`).
- **Symptom:** `stdout_reader` tracebacks in Cloud Run logs; MCP unreliable.
- **Root cause:** Spawning a child process and piping stdin/stdout is fragile in
  Cloud Run's serverless, sandboxed container.
- **Decision:** Since **GOOPHER is the only consumer** of these tools, MCP added
  failure surface and indirection without benefit. **Removed MCP entirely**
  (`49573fd`); registered inventory/order as **direct ADK function tools**
  (in-process). Renamed `app/mcp/` → `app/tools/`.
- **Trade-off accepted:** Lose "true MCP transport" (and external-client
  reusability) in exchange for reliability and simplicity. MCP only earns its
  keep when *external* clients (Claude Desktop, other apps) need the tools.
- **Lesson:** Don't adopt a protocol/pattern for its own sake; match the
  architecture to the actual consumer set and the runtime's constraints.

### 3.12 Dev-portal showed each sub-agent twice
- **Symptom:** modality/language/channel each appeared **twice** in the flow.
- **Root cause:** Both the **deterministic helpers** AND the real **ADK
  AgentTools** ran *and* both were recorded.
- **Fix (`d4b24c6`):** Deterministic helpers became **backup-only**; the portal
  attributes each invocation **once** based on the path taken (ADK AgentTools in
  production, deterministic "(backup)" only when ADK is off/errored).
- **Lesson:** Observability must reflect *what actually did the work*, not every
  code path that touched the data.

### 3.13 Hierarchy inversion — orchestrator demoted to "step 4"
- **Symptom:** The portal listed the pipeline as `memory → modality → language →
  goopher_orchestrator (step 4) → channel`, so the **main agent looked like a
  middle step**, not the root.
- **Root cause:** I wrapped everything in a `SequentialAgent` as the *root*,
  which made the orchestrator just one item in its `sub_agents` list — inverting
  the intended hierarchy (orchestrator should be ON TOP, others under it).
- **Fix (`8cdcc8d`):** Make `goopher_orchestrator` the **root LlmAgent**; all
  others are sub-agents exposed as AgentTools *under* it.
- **Lesson:** In a hierarchy, the coordinator is the root that *owns* the
  sub-agents — not a peer inside a sequence.

### 3.14 SequentialAgent cannot be wrapped as an AgentTool
- **Symptom (caught in Cloud Trace):** `execute_tool context_pipeline` showed a
  **red error**, and every turn silently fell back to the deterministic backup —
  even though memory_agent/modality_agent were visibly starting to run.
- **Root cause:** To keep "memory → modality → language always run in order"
  while keeping the orchestrator on top, I exposed a `SequentialAgent`
  (`context_pipeline`) to the orchestrator as an `AgentTool`. **That's an invalid
  combination** — an AgentTool expects a single agent that returns one response,
  but a SequentialAgent emits multiple sub-agent outputs, breaking the tool-call
  contract. The tool call crashed → whole turn fell back.
- **How Cloud Trace nailed it:** the waterfall showed the orchestrator on top,
  the sub-agents nesting correctly, AND the red `execute_tool context_pipeline`
  span — pinpointing the exact failing node. (The dev portal alone only showed
  "(backup) ran"; the trace showed *why*.)
- **Fix (`70206c9`):** Expose memory/modality/language as **individual**
  AgentTools (plain LlmAgents that return cleanly); enforce ordering via the
  orchestrator instruction instead of a wrapper.
- **The deeper trade-off (unresolved tension):** There is a genuine conflict
  between two goals:
    * *Orchestrator on top + flexible* → AgentTools, but the LLM may skip a
      sub-agent it deems unneeded (ordering is instruction-enforced, not forced).
    * *All sub-agents guaranteed in fixed order* → a `SequentialAgent` as ROOT,
      but then the orchestrator is a step inside it, not the parent.
  You cannot have both with one simple structure. We chose orchestrator-as-root
  with instruction-enforced ordering.
- **Lessons:**
  1. Not every ADK agent type composes with every wrapper — `SequentialAgent`
     ≠ `AgentTool`-compatible. Check the contract before nesting.
  2. **Cloud Trace is the diagnostic of record** for multi-agent failures: a
     red span on the exact node beats guessing from a fallback symptom.
  3. "Guaranteed order" and "smart, on-top orchestrator" are in tension; pick
     deliberately rather than assuming one structure gives both.

---

## 4. Key trade-offs and decisions

| Decision | Options | Chosen | Why |
|---|---|---|---|
| **LLM provider** | Gemini (free/Vertex) vs OpenAI | Both, switchable (`LLM_PROVIDER`) | Gemini for the $300 credit + ADK; OpenAI as a no-quota local fallback. Kept Gemini paths even when on OpenAI. |
| **Tool transport** | MCP vs direct ADK function tools | Direct (in-process) | MCP-stdio failed in Cloud Run; single consumer doesn't justify the indirection. |
| **Multi-agent design** | Real AgentTools (more LLM calls) vs deterministic | Real AgentTools, deterministic as backup | The deliverable goal was *visible* agent orchestration (Cloud Trace + dev portal). Accepted ~4–5 LLM calls/turn (cost/latency) for that. |
| **Sub-agent execution** | Both run vs one | Backup-only deterministic | Eliminates double work + duplicate traces. |
| **Conversation memory** | In-process dict vs Firestore | Firestore in cloud, dict locally | Dict loses context across Cloud Run instances/scale-to-zero; Firestore is shared + durable. |
| **Access control** | Open vs allowlist vs network IAM | Email allowlist + master password, **fail-closed** | Locks the LLM to one user without breaking the simple extension login. |
| **Rate limiting** | In-process vs Redis/Firestore-backed | In-process sliding window | Dependency-free; per-instance is enough for a single-user service (honest caveat documented). |
| **Dev portal access** | Auth'd vs open | Open (per request) | CTO demo convenience; one env flag (`DEV_PORTAL_ENABLED`) disables it. |
| **Resilience** | LLM-only vs fallback | Deterministic fallback engine | Service stays useful (grounded answers) during LLM outage/quota; keeps tests hermetic & offline. |
| **Dependency pinning** | Exact pins vs ranges | Ranges (`>=`) | Exact pins caused a hard `mcp`/`google-adk` resolution conflict. |

---

## 5. Security learnings (some painful)

- **Leaked credentials in chat (twice):** A Gemini API key and a GCP
  service-account **private key** were pasted into the conversation. Actions
  taken: never committed them (`.env` gitignored; `git log` verified clean),
  **deleted/rotated** the SA key immediately (`gcloud iam ... keys delete`), and
  established the rule: *secrets go only into the Cloud Shell editor → straight
  into GitHub Secrets → delete the local file; never into chat or
  `.env.example`.*
- **Fail-closed auth:** If `MASTER_PASSWORD` is unset, **all** logins are
  rejected — a misconfiguration can never silently leave the endpoint open.
- **Constant-time password compare** (`hmac.compare_digest`) to avoid timing
  leaks.
- **Commit-message hygiene:** stripped a co-author trailer from all 50 commits
  via `git filter-branch --msg-filter` (history was unpushed, so safe).
- **Honest residual risk:** the endpoint is still publicly *reachable* (returns
  401 to outsiders); true network-level lockdown (Google identity token on every
  request) was offered but not adopted to keep the extension login simple.

---

## 6. Process learnings (how we worked)

- **Verify, don't assume.** The two most embarrassing moments — claiming the
  "JCPenney refusal" was fixed when the edit silently failed, and claiming
  secrets were saved when `GCP_SA_KEY` wasn't — both came from *not verifying*.
  Live testing and `git ls-files`/grep checks caught them.
- **Read the actual error.** Every CI/CD failure had a precise cause in the log
  (empty `SHORT_SHA`, `limit: 0`, `Bad syntax for dict arg`, YAML indentation).
  Guessing wasted cycles; reading the literal error fixed it.
- **One layer at a time.** The CI/CD chain only resolved by fixing each distinct
  failure in sequence rather than rewriting everything.
- **Prefer structural fixes.** Version ranges (not pins), `--env-vars-file`
  (not string concatenation), IAM roles (not `--suppress-logs` band-aids).
- **Keep a reliable fallback.** The deterministic engine meant the product never
  hard-failed during LLM/quota/ADK turbulence and kept tests fast and offline.
- **Tooling friction is real.** Output-relay hiccups and cp1252 console encoding
  (emoji crashed eval output on Windows) were solved with ASCII-safe output and
  writing results to files.

---

## 7. Final architecture (after all the iteration)

```
Chrome extension "GOOPHER" (MV3 side panel)  ──HTTPS+JWT──►  Cloud Run (FastAPI)
  · login (allowlist + master password)                       │
  · channel/language toggles, 🎤 voice (popup), 🔊 TTS          │
                                                               ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │  RateLimit + size-limit middleware  →  Auth (fail-closed)           │
   │  ADK orchestrator (Gemini 2.5-flash on Vertex AI, $300 credit)      │
   │    ├─ AgentTool: modality_agent / language_agent / channel_agent    │
   │    └─ function tools: inventory_search / order_status / bulk ...     │
   │  Deterministic fallback engine (backup, no-LLM path)                │
   │  Firestore memory (sessions) · Cloud Trace · /metrics · /dev portal │
   └───────────────────────────────────────────────────────────────────┘
                                                               ▼
                               Firestore (catalog, orders, customers, sessions)

CI/CD: push to main → GitHub Actions → test+eval → Cloud Build → Cloud Run
       (Vertex/Gemini env, public invoker, prints URL)
Storefront "Marketplace" served at /  ·  Developer portal at /dev (live SSE)
```

---

## 8. What's done vs. deliberately deferred

**Done & verified:** mock data (2 departments), search relevance, multi-agent
ADK orchestration on Vertex (traced), Firestore data + memory, single-user
lockdown, rate limiting/size limits, Docker, **fully automated CI/CD**, live
developer portal, 53 unit tests + 8 evals.

**Deferred (with honest reasons):**
- **Secret Manager** (currently Cloud Run env vars) — standard hardening, not yet
  done.
- **CORS locked to extension origin** (currently `*`).
- **Network-level IAM lockdown** (endpoint still publicly reachable).
- **Firestore-backed rate limiting / dev-portal buffer** — current ones are
  per-instance; fine for single-user, not strictly global under autoscaling.
- **Real identity (Firebase Auth)** — still a master-password model.
- **Direct unit test of `FirestoreStore`** — interface-tested + manually
  verified, but no emulator/mock test yet.
- **Cost of 4–5 LLM calls/turn** — accepted for trace visibility; could be
  optimized by making language/channel deterministic-only.

---

## 9. One-line takeaways

1. A reliable **deterministic fallback** turns LLM/quota/cloud flakiness from an
   outage into a degraded-but-working experience.
2. **Quota errors lie** — distinguish `limit: 0` (wrong model) from daily caps.
3. **Reasoning models spend output budget on thinking** — size tokens + parse
   defensively.
4. **CI/CD to a real cloud is a chain of small, distinct failures** — fix one
   layer at a time, read the literal error.
5. **Don't adopt a protocol (MCP) for its own sake** — match architecture to the
   actual consumers and runtime.
6. **Verify edits and secrets actually applied** before declaring success.
7. **Never paste secrets into chat**; fail-closed everywhere; rotate on leak.
8. **Observability should reflect what truly executed**, not every code path.
9. **Agent types don't all compose** — a `SequentialAgent` can't be an
   `AgentTool`; verify the contract before nesting ADK agents.
10. **"Guaranteed order" vs "smart orchestrator-on-top" is a real tension** —
    one simple structure won't give both; choose deliberately.
11. **Cloud Trace is the multi-agent diagnostic of record** — a red span on the
    exact failing node beats guessing from a fallback symptom.
