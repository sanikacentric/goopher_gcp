# GOOPHER — Autoscaling Cheatsheet (copy-paste)

**Service:** `goopher-api` · **Region:** `us-central1` · **Project:** `<your-project-id>`
**URL:** `https://<your-service>.a.run.app`
**Cloud Run metrics:** `https://console.cloud.google.com/run/detail/us-central1/goopher-api/observability/metrics?project=<your-project-id>`
**Cloud Trace:** `https://console.cloud.google.com/traces/list?project=<your-project-id>`

> **Shell note:** **Cloud Shell = bash** (single-line, `\` to wrap). **Your laptop = PowerShell**
> (backtick `` ` `` to wrap). The `gcloud` commands run in **Cloud Shell**; the `python` load test
> runs in **PowerShell** (or Cloud Shell).

---

## WHY this approach (say this if asked)
- **Two load modes on purpose.** `/sim/chat` is **read-only, no-LLM, no-writes** → it isolates the
  **app's horizontal scaling** (the model-independent property) so we can ramp to thousands **without
  burning LLM tokens or quota**. `/chat` drives the **real Gemini path** to prove the LLM side is
  healthy under concurrent load. Different tools prove different things.
- **Load-test the same endpoints the extension calls.** The extension is a per-user client (UI runs
  in each browser); the only shared resource is the backend API. `/chat` is the exact call the
  extension makes → proving the backend autoscales **is** proving 10,000 extensions work.
- **Autoscaling is config, not code.** It's a **Cloud Run capability** that works because the app is
  **stateless** with state in **Firestore**. Capacity = `concurrency × max-instances` — a dial.
- **Why a rate-limit exemption for `/sim`.** A load generator hits from **one IP**; GOOPHER's
  abuse-protection rate limiter (120 req/min/IP) would 429 the test. `/sim/*` is exempt so the test
  measures **Cloud Run**, not the limiter. **`/chat` keeps its limit** (real abuse protection) — we
  raise it *temporarily* only for the LLM run.

---

## 0 · ONE-TIME SETUP (already done — verify only)
The scale dials are baked into `deploy.yml`, so a normal deploy sets **Min 1 / Max 20 / concurrency 80**.
Verify (Cloud Shell):
```bash
gcloud run services describe goopher-api --region us-central1 --format="value(spec.template.metadata.annotations)"
# expect: ...maxScale=20;minScale=1...
curl https://<your-service>.a.run.app/sim/stats   # expect backend=firestore, a counter
```
> Free-trial quota caps total CPU at **20 vCPU**, so `max-instances 20 × cpu 1` is the ceiling here.
> On a paid account, raise `--max-instances` and the ceiling lifts — same mechanism.

If the dials ever read Min 0 / Max 2/3, a deploy reverted them — re-apply (Cloud Shell, one line):
```bash
gcloud run services update goopher-api --region us-central1 --concurrency 80 --max-instances 20 --min-instances 1 --cpu 1 --memory 1Gi
```

---

## 1 · NON-LLM scale demo (the headline — "100 → ~1000 users")
No setup needed (`/sim` is rate-limit-exempt). Run in **PowerShell** (or Cloud Shell):
```powershell
python scale/loadtest.py --url https://<your-service>.a.run.app --stages 50,150,400,800 --duration 20
```
**Steps while it runs:**
1. Watch the terminal table → **OK% ~100%**, errors ~0, RPS rising.
2. Open **/sim/stats** tab → refresh → `sim_requests_served` climbs into the tens of thousands.
3. Open **Cloud Run METRICS** → **Container instance count** steps **1 → up to 20**.

**Modes:** `--mode browse` (product support) · `--mode order_status` (order mgmt) · `--mode mixed` (both).
**Push the cap on purpose:** add a `1000` stage → ~93% OK = saturating 20 instances → *"lift the quota, lift the ceiling."*

---

## 2 · REAL-LLM scale demo ("but real users use the LLM!")
`/chat` is rate-limited (20/min) + needs auth. Temporarily raise the limit, run small, then restore.

**Step A — raise the rate limit (Cloud Shell; keeps the dials):**
```bash
gcloud run services update goopher-api --region us-central1 --update-env-vars RATE_LIMIT_CHAT_PER_MIN=100000,RATE_LIMIT_GLOBAL_PER_MIN=100000
```
**Step B — run the real-LLM test (PowerShell; SMALL stages — uses real tokens):**
```powershell
python scale/loadtest.py --url https://<your-service>.a.run.app --endpoint /chat --email demo@goopher.app --password "<DEPLOYED_MASTER_PASSWORD>" --stages 5,10,20 --duration 10
```
> Use the **GitHub-secret `MASTER_PASSWORD`** value (the deployed one), NOT the local `.env` one.
> Product questions only → nothing is purchased. Expect ~1–3s latency, high OK% at 5–20 concurrent.

**Step C — RESTORE the rate limit after the demo (don't skip):**
```bash
gcloud run services update goopher-api --region us-central1 --update-env-vars RATE_LIMIT_CHAT_PER_MIN=20,RATE_LIMIT_GLOBAL_PER_MIN=120
```
**Say:** *"Real Gemini conversations, concurrent users, healthy. Higher sustained QPS → **Vertex
Provisioned Throughput** (reserved capacity + SLA); and if the model throttles, GOOPHER degrades
gracefully to grounded answers instead of failing."*

---

## 3 · Narrate the Cloud Run dashboard (point at each panel)
| Panel | VP (business) | CTO (technical) |
|---|---|---|
| **Container instance count** ⭐ | "capacity added by itself as customers arrive" | "instances autoscale 1→20 on concurrency" |
| **Request count** | "interactions handled at once — thousands" | "throughput (RPS) rising under load" |
| **Request latency** | "how fast each customer gets a response" | "p50/p95/p99; bounded p95 = healthy" |
| **Billable instance time** ⭐ | "pay only for the busy time; ~$0 idle" | "per-instance-second billing; scale-to-zero" |

**Closing:** *"As load rises, GOOPHER adds capacity automatically, stays fast, and you pay only for
what you use — no re-architecture, no over-provisioning."*

---

## 4 · CLEANUP after the interview (optional — saves cost)
```bash
# back to scale-to-zero (no always-on instance) once you're done demoing:
gcloud run services update goopher-api --region us-central1 --min-instances 0
# (rate limits: make sure you ran Step C above to restore 20/120)
```

---

## TROUBLESHOOTING (the 3 issues we hit)
| Symptom | Cause | Fix |
|---|---|---|
| **~95% errors, fast failures** on `/sim` | rate limiter 429s the single-IP test | already fixed: `/sim` is exempt — just re-run after deploy |
| **Header stuck on Min 0 / Max 2-3** | a CI/CD deploy reverted the dials, OR cached console | dials are now in `deploy.yml` (persist); hard-refresh (Ctrl+R) the console; `describe` is the truth |
| **`Max instances must be 20 or fewer`** | free-trial CPU quota = 20 vCPU | use `--max-instances 20` (paid account → request a quota bump) |
| **`/chat` test all 429 / can't log in** | `/chat` rate limit + wrong password | do Step A (raise limit); use the **deployed** master password |
| **bash hangs at `>`** | used PowerShell backtick `` ` `` in Cloud Shell | Cloud Shell is bash → run as **one line** (no backticks) |

---

## TL;DR — the 3 commands you actually need
```bash
# verify dials (Cloud Shell)
gcloud run services describe goopher-api --region us-central1 --format="value(spec.template.metadata.annotations)"
```
```powershell
# non-LLM headline run (PowerShell)
python scale/loadtest.py --url https://<your-service>.a.run.app --stages 50,150,400,800 --duration 20
```
```powershell
# real-LLM run (after raising the rate limit in Cloud Shell)
python scale/loadtest.py --url https://<your-service>.a.run.app --endpoint /chat --email demo@goopher.app --password "<PW>" --stages 5,10,20 --duration 10
```
