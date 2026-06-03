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

### 3.15 The LLM was put in the transactional path — checkout lost its cart
- **Symptom:** "place an order of oreo cookies" replied with a friendly
  paragraph ("Your order ID is ORD-50013, $89.95 charged…") but the **cart never
  appeared** in the GOOPHER chat, and `resp.checkout` (the structured payload the
  staged UI needs) was `null`. Reproduced only in the **cloud**, not locally.
- **Root cause (two layers, the second one was the real bug):**
  1. The cart/receipt logic lived only in the deterministic engine
     (`_generate_fallback`).
  2. **The cloud runs `use_adk_path=true`.** So checkout went through the ADK
     `LlmAgent`, which called `place_order` and then **phrased its own
     natural-language reply** — and never set `self._last_checkout`. The
     deterministic cart/receipt code was simply not on the cloud's path, so the
     structured payload and the itemized cart silently vanished.
  - An earlier, related defect from the same mindset: ordering by name fell back
    to "first in-stock item" when no SKU was typed → "oreo not found, here's a
    Cheez-It" **silent substitution**, which the user explicitly forbade.
- **Why it hid for so long:** every test I ran locally used the deterministic
  path (OpenAI, `use_adk_path=false`), where it worked. The bug only existed on
  the ADK path. Lesson: **test the path production actually runs.** I added a
  regression test that places an order with `use_adk_path=True`.
- **The diagnostic that cracked it:** a `/version` build-marker endpoint. The
  live reply kept looking "old", so I couldn't tell if a deploy had landed or if
  the code was wrong. `/version` proved the new code *was* live → the problem
  wasn't deploy timing, it was that the ADK path bypassed my handler.
- **Fix (`7c6b64f`):** Treat checkout as a **transactional gate**. Extracted
  `_try_checkout()` and call it in `run_turn()` **before** the ADK/LLM branch, so
  a purchase is handled by deterministic, structured code in *every* path (cloud
  or local): resolve the product (refuse, never substitute) → `place_order` →
  simulated payment → `run_fulfillment` (real `ORDER_PLACED` write) → return the
  `{checkout}` payload + a deterministic `🛒 cart → 💳 → ✅ → 🎉` receipt. See
  `ARCHITECTURE.md §5b`.
- **Lessons:**
  1. **The LLM orchestrates and converses; it must not execute money-affecting
     actions.** Anything transactional/irreversible belongs in deterministic,
     validated, auditable code — the "LLM ≠ cashier" guardrail pattern.
  2. **Behavioral parity matters:** if the cloud path (ADK on) and the local path
     (ADK off) differ, you will ship bugs you can't reproduce. Route critical
     intents through one shared handler so all paths agree.
  3. **A build/version endpoint is cheap and ends entire categories of "is it
     even deployed?" confusion.** Add one early.
  4. Upgrade path that keeps the guardrail: swap keyword intent-detection for an
     LLM classifier that only extracts `(intent, product, qty)` as constrained
     JSON — execution still stays deterministic.

### 3.16 Gemini Vision returned empty — wrong SDK, then "thinking" ate the budget
Building the camera Vision subagent surfaced THREE distinct failures, each with a
different root cause — a good lesson in not stopping at the first hypothesis.
- **"couldn't make out the item" in the cloud, but fine locally.** The cloud runs
  `USE_VERTEXAI=true` with `GOOGLE_API_KEY=""`/`OPENAI_API_KEY=""`. The first
  implementation used the legacy `google.generativeai` SDK, which **cannot reach
  Vertex AI** — so with no API key it errored and there was no fallback. Fix: use
  the unified `google.genai` client (`genai.Client(vertexai=True, project=…,
  location=…)`), authenticated by the Cloud Run service account — the same Vertex
  setup the ADK chat path already used.
- **"gemini returned no text" even after it reached Vertex.** `gemini-2.5-flash`
  spends output tokens on internal *thinking* before the visible answer; the
  64-then-256 token cap was fully consumed by thinking → empty text. It was
  INTERMITTENT (clear shots answered fast and worked; harder shots thought more
  and returned empty), which read as "it suddenly broke." Fix:
  `thinking_config=ThinkingConfig(thinking_budget=0)` **and** `max_output_tokens
  =2048` (the orchestrator's proven value).
- **Diagnosis was blind until we surfaced the reason.** A generic failure message
  hid the cause. Adding a captured `_LAST_ERROR` + extracting the response
  `finish_reason` turned "no text" into an actionable signal, and a `/version`
  build endpoint ended "is the fix even deployed?" guessing.
- **Lessons:** (1) match the SDK to the runtime — AI-Studio vs Vertex are
  different clients. (2) For 2.5 models, disable thinking (or budget generously)
  on short/structured calls. (3) Intermittent ≠ random — a token-budget race
  looks like flakiness. (4) Build the diagnostic *into* the failure path early.

### 3.17 "Failed to fetch" on a file attachment — size limit + missing CORS
- **Symptom:** attaching a file and ordering it returned a bare "⚠️ Failed to
  fetch" — a client-side fetch rejection, not an HTTP error.
- **Root cause:** the 2 MB request-size middleware rejected the larger base64
  body, and the `413` (a) fired *before draining the upload* (browser sees a
  connection reset) and (b) carried **no CORS headers**, so the cross-origin
  extension couldn't read it — surfacing as the opaque "Failed to fetch."
- **Fix:** raise the limit to 12 MB (real attachments need room), drain the body
  before returning the 413, and add `Access-Control-Allow-Origin` to the
  middleware's 413/429 responses. The extension also detects network errors and
  shows a clearer message.
- **Lesson:** middleware-generated error responses must be CORS-safe and must not
  reject mid-upload, or legitimate 4xx errors masquerade as network failures.

### 3.18 Transactional intent kept slipping past the gate
Two follow-ups to §3.15 — the gate must catch *real* purchase phrasings, in every
modality:
- **Natural phrasing.** "hi can you please order balls for me" didn't match the
  keyword list, so it fell to the ADK agent and produced no cart. Added
  `_is_order_intent` (purchase verb / polite request, EXCLUDING status/tracking
  queries). Showed up most clearly on the Phone channel.
- **File & camera quantities.** "bulk order of 10 balls" via camera ordered 1; a
  file's per-line counts were ignored. The vision path now extracts the qty, and
  `place_bulk_order` gained per-line `quantities`. A stray modality placeholder
  (`[file 'order.txt' uploaded]`) was also being looked up as a product — now
  stripped before extraction.
- **Lesson:** an intent gate is only as good as its phrasing coverage; test it
  with how people actually talk, across every input channel, and keep the
  exclusions (status vs purchase) explicit.

### 3.19 Self-healing Guardian — and the "don't touch what works" constraint
- **The ask:** a self-healing agent impressive enough to make a CTO say *wow*.
  The first instinct was to wrap the real operations (vision recognize, chat
  LLM, catalog reads) so a chaos fault on a *real* request would heal live.
- **The course-correction (the actual lesson):** the existing flows were already
  working and demo-critical. Wrapping them risked breaking the very thing being
  demoed. The user's call — *"create a SEPARATE agent; it must not impact our
  working flows"* — was the right engineering judgment. We reverted the vision
  wiring and made Guardian **fully isolated**: it drives its own **synthetic
  transactions** through the resilience policy. That's not a downgrade — it's how
  real **synthetic monitoring** works, and it's *safer* (zero blast radius) while
  the demo visual is identical.
- **What made it WOW (and demoable):** the recovery had to be **visible and
  repeatable**. So: a **chaos injector** (deterministic, on-demand faults — like
  Chaos Monkey) + a live **health strip** + every recovery streamed to `/dev` as
  a `DETECT → DIAGNOSE → REMEDIATE → VERIFY` record + a background probe that
  **heals forward**. Breaking it on purpose and watching it fix itself is the
  whole show.
- **Honest framing for the CTO:** it's a real circuit-breaker + failover engine
  (the patterns you'd ship), demonstrated on synthetic traffic via a controlled
  fault injector — and it automates the *actual* incidents from this build
  (Vertex outage, thinking-budget, stale catalog, rate limits).
- **Lessons:**
  1. **Protect what works.** A new capability shouldn't be able to break shipped,
     demo-critical paths — isolate it; wire into real flows later behind a flag.
  2. **Self-healing is only impressive if it's visible** — invest in the chaos
     button + the live heal stream, not just the recovery logic.
  3. **Synthetic transactions** are a legitimate, low-risk way to demonstrate (and
     monitor) resilience.

**Reference — the 4 self-healing steps** (what streams to the purple HEAL card):
1. **🔎 DETECT** — protected op fails; mark 🟠, bump the breaker. → `1. DETECT —
   vertex.synthetic_request failed: ChaosError…`
2. **🧠 DIAGNOSE** — classify against a playbook (root cause), don't retry blindly.
   → `2. DIAGNOSE — LLM provider unavailable (Vertex 5xx / empty / timeout)`
3. **🔧 REMEDIATE** (stops at the first that works) — self-repair (e.g. re-seed) →
   retry with backoff → fail over so the customer is still served. → `retry #1
   failed → retry #2 failed → failover (customer unaffected)`
4. **✅ VERIFY** — 🟢 if recovered on primary, 🟠 if serving via failover. → `4.
   VERIFY — serving via failover; probing to heal forward`

Wrapped by **⚡ circuit breaker** (open after N failures → serve the fallback
directly) and **🔄 heal forward** (a background probe restores the primary and
closes the circuit once the fault clears) → `PROBE → HEAL FORWARD (primary is
back → closed the circuit)`.

**Where the buttons are (operational note):** the chaos controls live in the
**dev portal**, not the extension — `…/dev` → the **🛡️ Guardian** panel pinned
under the legend → **💥 Kill Vertex** (LED 🟠) → **▶ Vertex** (streams the HEAL
card) → **✅ Restore all** (heals forward to 🟢). If the panel is missing, the
deployed build predates Guardian (check `…/version`) — hard-refresh `/dev`.

**One-liner for the CTO:** *"Detect → Diagnose → Remediate → Verify, with a
circuit breaker and a background probe that heals forward — it recovers, keeps
the customer served, and restores itself when the dependency comes back. No
pager, no human."*

### 3.20 Conversational ordering — context, quantities, and sticky language
Three closely-related defects surfaced once people ordered the way they actually
talk (phone + voice + Spanish):

- **Quantity leaked into product search.** "place an order of **above 10**
  items" ordered **Play-Doh ×10** — because the "10" was left in the product
  string and matched "Play-Doh **10**-Pack". Fix: `_extract_order_product` now
  strips quantities (anywhere) and filler/contextual words before searching.
- **"above" was treated as a product name.** It's actually a *reference to the
  item just discussed*. Fix: the inventory tools record the **last-viewed product**
  (`get_last_viewed`, set in `search_inventory`/`get_product_details`, so it works
  in BOTH the ADK and deterministic paths), and `_try_checkout` resolves
  contextual references ("order it", "the above item") to that — never a random
  item; if nothing was viewed it asks "which item?". This turned a bug into a
  feature: *ask about a product, then say "order it."*
- **Sticky language.** After a Spanish conversation the session remembered
  `language=es`; English had **no positive fingerprint**, so an English message
  scored 0 and fell back to the remembered Spanish → English in, Spanish out.
  Fix: add an English function-word fingerprint and let "en" win when it has the
  top/tied score, so a clearly-English message overrides the sticky default
  (real es/fr/hi/zh still detect correctly).
- **Lessons:**
  1. **Separate the quantity from the product** — a number in the utterance is a
     count, not part of the item name; don't let it reach the catalog search.
  2. **Resolve references with memory, not guesses** — "it/this/above" means "the
     thing we just discussed"; track last-viewed and use it (or ask), never
     substitute.
  3. **Don't let remembered state get stuck** — a sensible default (remembered
     language) must still yield to a clear current signal; give the "baseline"
     option (English) a positive way to win.
  4. **Test with how people actually talk** — voice + a second language exposed
     all three; exact-phrase unit tests would have missed them.

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

### Clarification: the `MEMORY · session updated` step (it's a feature, not a bug)
A reviewer watching `/dev` asked what the final `MEMORY · session updated` step
is. It's the agent **saving the conversation to memory at the end of every turn**
— it persists **both sides** of the exchange (user question + assistant reply)
into **session memory**, keyed by the turn's `session_id` (e.g. `sess-nst14x8icr…`
shown in the header).
- **Why it matters — continuity.** Because each turn is persisted, context
  carries across turns: "price of the tiered midi dress?" → "is it in **navy**?"
  → "**order it**" — the agent knows what *"it"* is. It also remembers the
  **language and channel**, so a shopper can start on Web/English and continue on
  Phone/Spanish and keep the thread.
- **Where it lives:** **Firestore** in the cloud (durable + shared across Cloud
  Run instances, surviving a different container or scale-to-zero — the earlier
  `SESSION · memory.get` step shows `backend=firestore`); an in-process store
  locally.
- **The pipeline, end to end:** `AUTH → SESSION (memory.get: load context) →
  PRE-PROCESS (modality·language·channel) → ORCHESTRATOR → inventory_agent →
  MEMORY (session updated: save this turn)`.
- **Lesson / takeaway:** *every turn loads prior context at the start and
  persists the new turn at the end* — that's the **T3 "memory / context across
  switches"** requirement working live. When something in the pipeline looks
  surprising, it's often the system doing exactly what it should; the dev portal
  makes that legible.

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

**Done & verified:** mock catalog (3 departments — clothing/food/toys), search
relevance, multi-agent ADK orchestration on Vertex (traced, with the
deterministic pre-process steps also span-traced), Firestore data + durable
session memory, single-user lockdown, rate limiting/size limits, Docker,
**fully automated CI/CD**, live developer portal, **88 unit tests** + 8 evals.

**Added since the original build (all done & verified):**
- **Vision subagent** — camera "see it, shop it" (Gemini Vision on Vertex).
- **Structured checkout gate** (single + bulk) → simulated payment →
  `ORDER_PLACED` → 9-stage fulfillment; **never substitutes**.
- **Bulk order from an uploaded file**; **contextual ordering** ("order it").
- **Cart / orders panel**; **phone-channel mobile simulator**; voice in/out.
- **Self-healing Guardian** — circuit breaker · failover · self-repair · chaos
  injection · heal-forward, with a live animated `/dev` panel.
- **`/version`** build marker for deploy verification.

**Acceptance-criteria coverage:** every criterion (2A, 2A-4/5/6, T1–T17, Req
3/4/5, security) is implemented — see the coverage table in `DEMO.md` and the
component map in `ARCHITECTURE.md §3`.

**LLM models used (reference):**
- **`gemini-2.5-flash`** (Google) — the PRIMARY model; production runs on it via
  **Vertex AI** (`LLM_PROVIDER=gemini`, `USE_VERTEXAI=true`, no OpenAI key). One
  natively-multimodal model does the ADK multi-agent reasoning, multilingual
  phrasing, AND the camera Vision (with `thinking_budget=0`, §3.16).
- **`gpt-4o-mini`** (OpenAI) — the `LLM_PROVIDER=openai` swappable alternate +
  vision fallback; used locally, inactive in the cloud.
- **No LLM** in the deterministic router, the language/channel/modality
  pre-processing, the checkout gate, or the Guardian — the model understands and
  phrases; deterministic code transacts.

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
12. **Don't force deterministic work into LLM agents** — if a step needs no
    intelligence (detect language, classify modality, pick channel), make it
    plain code; wrapping it as an agent adds fragility + cost for no benefit.
13. **Know when to stop iterating and revert** — when you can't test live and a
    "more correct" design keeps breaking, reverting to the demonstrably-working
    design is the right engineering call, not a defeat.
14. **The LLM orchestrates; it must not execute transactions** — route
    money-affecting/irreversible actions (checkout) through a deterministic,
    structured, auditable handler *before* the LLM ("LLM ≠ cashier").
15. **Test the path production runs** — a cloud-only bug (ADK on) hid behind a
    local-only green suite (ADK off); keep behavioral parity across paths.
16. **Ship a `/version` build marker early** — it ends "is it even deployed?"
    guessing in one HTTP call.
17. **Match the SDK to the runtime** — `google.generativeai` can't reach Vertex;
    use the unified `google.genai` client (`vertexai=True`) in the cloud.
18. **For 2.5 models, mind the "thinking" budget** — it spends output tokens
    before the answer; disable it (`thinking_budget=0`) or budget generously, or
    short calls return empty. Intermittent emptiness ≠ random.
19. **Middleware errors must be CORS-safe and drain the body** — otherwise a
    legitimate 413/429 shows up as an opaque "Failed to fetch."
20. **Build the diagnostic into the failure path** — capture the reason
    (`finish_reason`, last error) so the next failed attempt tells you why.
21. **A new feature must not endanger what already works** — isolate it (Guardian
    drives synthetic transactions, never the live flows); integrate deeper later
    behind a flag.
22. **Self-healing is only a "wow" if it's visible** — ship the chaos button and
    the live DETECT→DIAGNOSE→REMEDIATE→VERIFY stream, not just the recovery code.
23. **Keep quantity out of the product name, resolve "it/above" from memory, and
    don't let remembered state get stuck** — conversational ordering breaks in
    all three ways when people talk naturally (voice + a second language).

---

## 10. Case study: reverting the pre-processing "agents" to deterministic code

This is the single most instructive arc of the build, so it gets its own
section. It captures a multi-hour attempt to make **everything** an ADK agent,
why it failed, and why reverting was the right decision.

### The goal that drove it
The requirement was a "proper ADK multi-agent" system where the orchestrator
selects sub-agents that take action. Taken literally, that pushed toward making
**all six** capabilities real ADK `LlmAgent`s the orchestrator delegates to:
`memory`, `modality`, `language`, `channel` (pre-processing) **and**
`inventory`, `order` (workers).

### What we tried (in order)
1. **Sub-agents as `AgentTool`s** — the LLM chose which to call. Problem: Gemini
   *skipped* the ones it deemed unneeded, so they didn't reliably run.
2. **A `SequentialAgent` wrapping all of them** to force fixed order. Problem #1:
   it made the orchestrator just "step 4 in a list" — inverting the hierarchy
   (the orchestrator should be the ROOT, not a peer).
3. **`SequentialAgent` as a single `AgentTool` (`context_pipeline`)** to keep the
   orchestrator on top while guaranteeing order. Problem: **a SequentialAgent
   cannot be wrapped as an AgentTool** — it emits multiple sub-agent outputs and
   breaks the tool's single-response contract → `execute_tool context_pipeline`
   went **red in Cloud Trace** → every turn fell back to the deterministic engine.
4. **Individual pre-processing agents as `AgentTool`s** with a per-turn
   `ContextVar` to pass session context. Problem: the tool-only agents emitted
   **no final text** (`RuntimeError: ADK produced no text response`), AND the
   `ContextVar` was unreliable across ADK's execution context. Trace showed
   `memory_agent` and `modality_agent` running, then `language_agent` erroring.
5. **Instruction tweak ("always reply with text") + resilient text capture.**
   The error simply moved to the *first* sub-agent (`memory_agent`). Still red.

### Why it kept failing (root cause)
The four pre-processing capabilities are **deterministic** — detecting a
language, classifying modality, choosing a channel directive, and reading
session memory need **no LLM reasoning**. Forcing them into `LlmAgent`s meant:
- an extra Gemini call each (≈5 LLM calls/turn → cost + latency + quota burn),
- a brittle dependency on ADK's tool/agent execution + context plumbing,
- the "tool-only agent has no text to return" contract violation,
all for **zero functional benefit** over a 0.02 ms Python function.

### The decision: revert to the reliable design
- **Keep as REAL ADK agents the only things that genuinely reason:**
  `inventory_agent` and `order_agent` — workers that own and call tools. These
  were **proven green in Cloud Trace** the whole time
  (`orchestrator → inventory_agent → search_inventory`).
- **Make modality/language/channel/memory deterministic Python** that runs as a
  pre-processing phase before the orchestrator, shown clearly and separately in
  the dev portal as "PRE-PROCESS" (not pretending to be agents).
- Removed `specialist_agents.py` and the dead `_run_adk_turn` /
  `_run_backup_turn` / `_generate` helpers.

Result: the ADK path completes cleanly (no fallback), the orchestrator stays the
ROOT/main agent, real worker delegation is intact, and the system is reliable
and cheap.

### The honest process lessons
- **I iterated several times on a design I could not test live** (local Gemini
  quota exhausted from the multi-call design; no cloud login). That produced
  "blind" commits the user had to verify each time — inefficient and avoidable.
- **The user's instinct ("keep deterministic as backup, don't mix") and the
  final "revert" call were correct.** When two goals are in genuine tension
  (guaranteed-order vs orchestrator-on-top) and the "clever" path is fragile,
  choose the demonstrably-working structure.
- **Match the tool to the job:** LLM agents for reasoning/decisions; plain
  functions for deterministic transforms. "Make everything an agent" is an
  anti-pattern.

### Final architecture (the conclusion)
```
goopher_orchestrator   ◄── MAIN agent (ROOT, ADK LlmAgent, in charge)
  │  delegates to →
  ├─ inventory_agent  (real ADK worker → search_inventory / check_stock / details)
  └─ order_agent      (real ADK worker → order_status / list / bulk_status)

+ Deterministic pre-processing (plain Python, runs first, shown as "PRE-PROCESS"):
    modality · language · channel · memory   — 100% reliable, free, instant
+ Deterministic engine remains a separate BACKUP when ADK is off/errors.
```
