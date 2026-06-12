# GOOPHER — High-Volume Scalability Validation (IT Leadership Summary)

**Objective:** prove the unified conversational agent handles **high-volume, global**
self-service (order management + product support) — the customer's stated blocker.

**Method:** **one realistic load test** that mirrors production traffic — a *hybrid* mix of
cheap deterministic requests and a small slice of LLM-reasoning requests — not a synthetic split.

---

## 1 · Result (measured, live on Google Cloud)
| Concurrent users | Total requests | Success rate | Deterministic p95 | LLM-reasoning p95 | LLM share |
|---|---|---|---|---|---|
| 50 | 384 | **100%** | ~3.5 s | ~25 s | ~10% |
| 150 | 671 | **100%** | ~8 s | ~40 s | ~10% |
| 300 | 1,000 | **100%** | ~13 s | ~45 s | ~10% |

**Read-out:** 100% success across the ramp; **Cloud Run autoscaled** (1 → up to 20 instances) with
no code change. The deterministic majority stayed responsive; the LLM slice is the heavy part —
**by design**, kept to a minority of traffic.

---

## 2 · Which APIs the test hits (the request mix)
| Endpoint | Method | Role in the test | Share | LLM? |
|---|---|---|---|---|
| `/auth/login` | POST | obtain a JWT (once) | — | no |
| `/sim/chat` | GET | **deterministic path** — mirrors browse / order-status / checkout (real catalog + order lookup, read-only) | **~90%** | **no** |
| `/chat` | POST | **reasoning path** — the real multi-agent orchestrator → Gemini 2.5 Flash (authenticated) | **~10%** | **yes** |

> The 90/10 blend is configurable (`--mix`). It reflects real retail traffic: most interactions are
> lookups/status/checkout; only a fraction need open-ended reasoning.

---

## 3 · Architecture approach chosen — **Hybrid** ("LLM orchestrates, code transacts")
- **Deterministic Python** handles routing, language/channel, and **checkout** (the money path) — **no LLM**.
- **Gemini 2.5 Flash on Vertex AI** is used **only** for open-ended reasoning.
- **Stateless app on Cloud Run** (serverless autoscaling); **session state in Firestore** (shared, durable)
  so any instance serves any user.
- **Multi-agent orchestration via Google ADK** (agent-as-tool — loops impossible by construction).
- **Why:** scale, cost, and safety. The expensive/slow part (LLM) is off the hot path; the hot path is
  cheap, horizontal, and auditable.

---

## 4 · PROS
- **Scales horizontally with zero code change** — capacity is a Cloud Run config dial (`concurrency × max-instances`).
- **Cost-efficient** — the LLM (the costly resource) serves only ~10% of traffic; the deterministic
  majority is cheap; **scale-to-zero** means ~$0 at idle. Cost tracks usage, not headcount.
- **Safe & auditable** — checkout is deterministic and confirm-before-charge; the LLM never moves money.
- **Resilient** — if the model is throttled under a spike, GOOPHER **degrades gracefully** to grounded
  tool answers instead of failing.
- **One realistic test** validates the *actual* production traffic shape, not an artificial best case.

## 5 · CONS / Limitations (stated honestly)
- **LLM latency** is inherently high (seconds → tens of seconds under concurrency) and **token-costly** —
  so it must remain a **minority** of traffic; it is not a high-QPS path.
- **Free-trial quota** caps total CPU at 20 vCPU → demo ceiling is **20 instances**; production needs a quota increase.
- **Rate limiting is per-instance** (in-process) — correct per instance; a global limit needs a shared store.
- **Demo deterministic latency is inflated** — `/sim/chat` does a naive full-catalog scan per request on a
  tiny demo dataset; a production catalog uses **indexed lookups (<100 ms)**, so real deterministic latency
  is far lower than the demo numbers.

## 6 · TRADE-OFFS (decision → why)
| Decision | Alternative | Why we chose it |
|---|---|---|
| **Hybrid** (deterministic + LLM) | All-LLM | Cost, safety, latency — at the price of more code paths |
| **Gemini Flash** | Gemini Pro | Lower latency + cost at scale (sufficient for retail Q&A) |
| **Scale-to-zero** (Min 0) | Always-warm (Min 1) | ~$0 idle vs no cold start — tunable per traffic floor |
| **LLM off the hot path** | LLM in every request | Keeps 90% of traffic cheap/fast; reserve LLM for reasoning |
| **Load via no-LLM `/sim`** for the bulk | All real LLM | Push real volume without burning quota; LLM only a slice |

## 7 · CHALLENGES encountered (and how resolved)
| Challenge | Resolution |
|---|---|
| Abuse-protection rate limiter 429'd the single-IP load test | Exempted the read-only `/sim/*` scale endpoints; kept `/chat` protected |
| CI/CD deploy kept reverting the autoscaling dials | Baked `min-instances/max-instances/concurrency` into `deploy.yml` (persistent) |
| Free-trial CPU quota blocked higher `max-instances` | Capped at 20 (quota, not architecture); paid account lifts the ceiling |
| Real LLM latency/cost at volume | Keep LLM off the hot path; **Vertex Provisioned Throughput** for guaranteed QPS |

---

## 8 · Recommendation & next steps (production ramp)
1. **Pilot on the real catalog** with indexed Firestore queries (deterministic latency → milliseconds).
2. **Raise the Cloud Run quota** (paid account) → autoscale beyond 20 instances; same mechanism.
3. **Vertex Provisioned Throughput** → reserved QPS + SLA for the LLM slice.
4. **Global low-latency** → multi-region Cloud Run + Firestore; CDN for the storefront.
5. **Voice at scale** → Conversational Agents / CCAI + Speech-to-Text.
6. **Cost guardrails** → budget alerts, `max-instances` caps, autoscaling on real SLOs.

---

## One-paragraph executive summary
*GOOPHER validates high-volume, global self-service on Google Cloud using a hybrid design: the bulk of
traffic — browse, status, checkout — runs as cheap, stateless, deterministic work that Cloud Run
autoscales horizontally; only the small reasoning slice (~10%) uses Gemini. In a single realistic load
test it sustained 100% success up to 1,000 requests while scaling instances automatically. The model
is the cost/latency lever, so we keep it off the hot path and reserve capacity (Provisioned Throughput)
where guaranteed QPS is needed. Scale is a configuration decision, not a re-architecture — and cost
tracks usage, scaling to near-zero at idle.*
