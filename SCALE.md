# GOOPHER at Scale — "100 → 10,000 users" (high-volume playbook)

**The blocker (from the brief):** *"A global retail customer wants a modern self-service
solution to handle **high-volume** order management and product support via chat and voice…
for their **diverse global** customer base."*

**The claim you'll prove live:** GOOPHER is a multi-agent system that **auto-scales to
thousands of concurrent users** on Google Cloud — **with no code change** — because it's
**stateless, serverless, and async**, and because most traffic never needs an LLM call.

> One-liner for the VP: *"It scales like a website, not like a model — so cost tracks usage
> and we don't fall over on Black Friday."*

---

## Why GOOPHER scales (the architecture story)
| Design choice | Why it scales |
|---|---|
| **Stateless app on Cloud Run** | every request is independent → Cloud Run adds instances automatically; any instance serves any user. |
| **Session state in Firestore, not in memory** | a user's context lives in a **shared serverless DB**, so requests can land on *any* instance — horizontal scale with continuity. |
| **Async FastAPI** | high I/O concurrency per instance (many in-flight requests each). |
| **Cloud Run concurrency × max-instances** | e.g. **80 req/instance × 100 instances = 8,000 concurrent** — a config dial, not a rewrite. |
| **Deterministic pre-processing + gate** | modality/language/channel/routing and **checkout** run as plain Python — **no LLM call**, so the hot path is cheap and fast. |
| **Grounded fallback engine** | if Gemini is rate-limited under a spike, GOOPHER still answers from tools — **degrade, don't fail**. |
| **Bulk endpoints** (`/orders/bulk`) | high-volume **order management** in one call, not N round-trips. |
| **Self-healing Guardian** | absorbs dependency blips under load instead of cascading. |

**Net:** the expensive part (Gemini) is used **only when reasoning is needed**; everything else is
serverless and horizontal. That's what makes 10,000 users a **dial**, not a re-architecture.

---

## The live demo (3 min, drop it in after the main journey)
**Goal:** show flat latency + rising throughput as users climb → Cloud Run scaling out.

1. **Show the volume baseline:** open **`/sim/stats`** — catalog size, model, backend, and a live
   `sim_requests_served` counter.
2. **Run the load generator** (a second terminal / Cloud Shell):
   ```bash
   pip install httpx
   python scale/loadtest.py --url https://<your-cloud-run-url> --stages 50,200,500 --duration 8
   ```
   It prints a table per stage:
   ```
     USERS      REQS       RPS    p50ms   p95ms   p99ms     OK%    ERR
     ----------------------------------------------------------------------
        50      4012       501       95     140     190   100.0      0
       200     15880      1985       98     150     210   100.0      0
       500     38120      4765      105     165     240    99.9      4
   ```
   **Narrate:** *"Throughput climbs with users while latency stays flat — that's Cloud Run
   adding instances. No code changed; we just sent more traffic."*
3. **Show it in Google Cloud:** Cloud Run → **goopher-api → METRICS → Container instance count** —
   the instance line **steps up** under load and back to zero after. *"You pay for the steps,
   nothing at idle."*
4. **The headline run (10,000):** raise the scale dials first (below), then
   `--stages 100,1000,5000,10000 --duration 15` from Cloud Shell.

> The `/sim/chat` target is **read-only, no-LLM, no-writes** — safe to hammer live. It still runs
> the *real* deterministic routing + a *real* catalog/order lookup, so you're load-testing the
> genuine request + DB path, just without the LLM cost. (`mode=browse` = product support,
> `mode=order_status` = order management, `mode=mixed` = both.)

---

## Bonus demo — prove the REAL LLM path scales too (for "but real users use the LLM!")
The same tool can drive **genuine conversations through the orchestrator → Gemini** (authenticated),
so you can show the real path holds up under concurrent users. Keep concurrency **small** (it uses
real tokens/quota) and it asks **product questions only** — nothing is purchased.
```powershell
python scale/loadtest.py --url https://<your-cloud-run-url> --endpoint /chat `
  --email demo@goopher.app --password <MASTER_PASSWORD> --stages 5,15,30 --duration 10
```
You'll see higher (but bounded) latency — real LLM calls take ~1–3s — with **100% success** at
modest concurrency, and the Cloud Run instance count stepping up.
> **SAY:** *"These are real Gemini-backed conversations — concurrent users, still healthy. At very
> high sustained LLM QPS you'd reserve capacity with **Vertex Provisioned Throughput** for a
> guaranteed SLA. And because our hot path is deterministic, the LLM QPS we actually need is far
> lower than total traffic — so it's cheaper and never the bottleneck."*

**Why two modes:** `/sim/chat` isolates the **app's** horizontal scaling (model-independent, cheap to
push to 10k); `/chat` proves the **LLM** path is healthy under real concurrent load. Show the first
for the headline 10,000-user number, the second to answer "but real users use the LLM."

## The scale dials (apply before the 10k run — does NOT change app code)
The default demo deploy is capped small (cheap). For the headline run, raise the limits:
```bash
gcloud run services update goopher-api --region us-central1 \
  --concurrency 80 \        # requests served per instance
  --max-instances 100 \     # 80 × 100 = up to 8,000 concurrent; raise for more
  --min-instances 1 \       # 1 warm instance → no cold start on stage
  --cpu 1 --memory 1Gi
```
**Trade-off:** higher `max-instances` = higher *peak* cost during the spike, **$0 at idle**
(scale-to-zero). Concurrency vs. latency is a knob: more concurrency = fewer instances (cheaper)
but more work per instance.

---

## Honest trade-offs (defend these to the domain expert)
- **The LLM is the real scale/cost lever, not the app.** We keep it off the hot path
  (deterministic routing + checkout) and reserve Gemini 2.5 **Flash** (low-cost) for reasoning.
  For guaranteed QPS under sustained load → **Vertex Provisioned Throughput**.
- **Cold starts** at scale-to-zero: mitigated with `min-instances: 1` for the demo;
  in prod, size `min-instances` to your floor traffic.
- **Per-instance rate limit is in-process** (fine per instance); a global limit would move to a
  shared store (Memorystore/Firestore) — a known, scoped upgrade.
- **Firestore** handles the read/write volume serverlessly; hot single documents would shard —
  our session keys are per-user, so they spread naturally.

---

## Production ramp (the "next steps" slide)
1. **Voice at scale →** Conversational Agents / **CCAI** + Speech-to-Text (telephony-grade).
2. **LLM throughput →** Vertex **Provisioned Throughput** for predictable QPS/SLA.
3. **Global low latency →** multi-region Cloud Run + Firestore; Cloud Load Balancing + CDN for the storefront.
4. **Resilience →** the Guardian's circuit-breaker pattern + a queue (Pub/Sub) for bulk order spikes.
5. **Cost guardrails →** budget alerts, `max-instances` caps, autoscaling on real SLOs.

---

## One-paragraph answer if the CTO asks "how does this handle 10,000 users?"
*"GOOPHER is stateless and serverless — the conversation state lives in Firestore, so Cloud Run
just adds instances as traffic rises; concurrency × max-instances gives you the headroom as a
config dial. The expensive part — Gemini — is used only when reasoning is needed, because routing,
language/channel handling, and the checkout gate are deterministic Python. So the hot path is
cheap and horizontal, it degrades gracefully if the model is throttled, and it scales to zero when
idle. I can show you: here's a load test ramping to thousands of concurrent users with flat
latency, and the Cloud Run instance count stepping up live."*
