#!/usr/bin/env python3
"""
GOOPHER — high-volume load generator (prove Cloud Run autoscaling, 100 → 10,000 users).

Drives many concurrent "conversations" against the deployed service and prints a
live table per ramp stage: concurrency, throughput (RPS), latency p50/p95/p99,
and success rate. Targets the READ-ONLY, NO-LLM `/sim/chat` endpoint by default,
so you can push real volume without burning LLM quota or mutating data.

USAGE (run from anywhere with Python 3.10+ and httpx):
    pip install httpx
    # quick laptop demo:
    python scale/loadtest.py --url https://<your-cloud-run-url> --stages 50,200,500 --duration 8
    # the headline "10,000 users" run (use Cloud Shell / a VM, and raise Cloud Run
    # max-instances + concurrency first — see SCALE.md):
    python scale/loadtest.py --url https://<your-cloud-run-url> --stages 100,1000,5000,10000 --duration 15

Mix product-support + order-management traffic with --mode mixed.
NOTHING here mutates data — it's safe to run against the live demo.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

# Windows consoles default to cp1252 and choke on the arrows in the output.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

try:
    import httpx
except ImportError:  # pragma: no cover
    raise SystemExit("Install httpx first:  pip install httpx")

DEFAULT_URL = "https://goopher-api-7vnucwimtq-uc.a.run.app"
QUERIES = ["oreo cookies", "potato chips", "soccer ball", "lego", "soda",
           "dress", "peanuts", "play-doh", "crackers", "nerf"]


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, int(round((p / 100) * (len(s) - 1))))
    return s[k]


async def _worker(client, url, endpoint, mode, deadline, lat, counts, idx):
    i = idx
    is_sim = endpoint == "/sim/chat"
    is_real = endpoint == "/chat"   # REAL orchestrator → Gemini (authenticated)
    while time.monotonic() < deadline:
        q = QUERIES[i % len(QUERIES)]
        t0 = time.monotonic()
        try:
            if is_real:
                # product QUESTIONS only (no order/confirm) → nothing is purchased.
                body = {"message": f"do you have {q}?",
                        "session_id": f"load-{idx}", "channel": "web"}
                r = await client.post(f"{url}{endpoint}", json=body)
            elif is_sim:
                m = ("order_status" if (mode == "order_status" or (mode == "mixed" and i % 3 == 0))
                     else "browse")
                r = await client.get(f"{url}{endpoint}", params={"message": q, "mode": m})
            else:
                r = await client.get(f"{url}{endpoint}")  # e.g. /catalog, no params
            ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ok = False
        lat.append((time.monotonic() - t0) * 1000)
        counts[0 if ok else 1] += 1
        i += 1


async def _login(url: str, email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{url}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


async def run_stage(url, endpoint, concurrency, duration, mode, token=None) -> dict:
    lat: list[float] = []
    counts = [0, 0]  # [ok, err]
    limits = httpx.Limits(max_connections=concurrency + 50,
                          max_keepalive_connections=concurrency + 50)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    deadline = time.monotonic() + duration
    async with httpx.AsyncClient(timeout=60, limits=limits, headers=headers) as client:
        await asyncio.gather(*[
            _worker(client, url, endpoint, mode, deadline, lat, counts, i)
            for i in range(concurrency)
        ])
    total = counts[0] + counts[1]
    rps = total / duration if duration else 0
    return {
        "users": concurrency, "total": total, "ok": counts[0], "err": counts[1],
        "rps": rps,
        "p50": _pct(lat, 50), "p95": _pct(lat, 95), "p99": _pct(lat, 99),
        "ok_pct": (counts[0] / total * 100) if total else 0,
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description="GOOPHER high-volume load generator")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--stages", default="50,200,500",
                    help="comma list of concurrent-user counts to ramp through")
    ap.add_argument("--duration", type=float, default=8.0, help="seconds per stage")
    ap.add_argument("--mode", default="mixed", choices=["browse", "order_status", "mixed"])
    ap.add_argument("--endpoint", default="/sim/chat",
                    help="/sim/chat or /catalog (no-LLM), or /chat for the REAL LLM path")
    ap.add_argument("--email", default="demo@goopher.app", help="login for --endpoint /chat")
    ap.add_argument("--password", default="", help="master password for --endpoint /chat")
    args = ap.parse_args()

    stages = [int(s) for s in args.stages.split(",") if s.strip()]
    token = None
    if args.endpoint == "/chat":
        # REAL conversations through the orchestrator → Gemini (authenticated).
        if not args.password:
            raise SystemExit("--password is required for --endpoint /chat (the master password).")
        if max(stages) > 50:
            print("  ⚠️  REAL LLM mode: high concurrency uses real tokens/quota — "
                  "recommend small stages like --stages 5,15,30.\n")
        token = await _login(args.url, args.email, args.password)
        print("  ✅ logged in — driving REAL conversations (Gemini). Product questions only; "
              "nothing is purchased.")

    label = ("REAL LLM (/chat)" if args.endpoint == "/chat"
             else f"{args.endpoint} (no-LLM)")
    print(f"\n  GOOPHER load test → {args.url}   {label}   mode={args.mode}   {args.duration}s/stage")
    if args.endpoint != "/chat":
        print("  (read-only, no LLM, no writes — safe to run against the live service)\n")
    else:
        print()
    print(f"  {'USERS':>7} {'REQS':>9} {'RPS':>9} {'p50ms':>8} {'p95ms':>8} "
          f"{'p99ms':>8} {'OK%':>7} {'ERR':>6}")
    print("  " + "-" * 70)
    for c in stages:
        r = await run_stage(args.url, args.endpoint, c, args.duration, args.mode, token)
        print(f"  {r['users']:>7} {r['total']:>9} {r['rps']:>9.0f} {r['p50']:>8.0f} "
              f"{r['p95']:>8.0f} {r['p99']:>8.0f} {r['ok_pct']:>6.1f}% {r['err']:>6}")
    print("\n  ↑ flat latency + rising RPS as users climb = Cloud Run scaling out.")
    print("  Watch instances grow in: Cloud Run → goopher-api → METRICS → Container instances.\n")


if __name__ == "__main__":
    asyncio.run(main())
