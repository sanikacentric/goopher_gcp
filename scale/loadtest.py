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
    while time.monotonic() < deadline:
        if is_sim:
            q = QUERIES[i % len(QUERIES)]
            m = ("order_status" if (mode == "order_status" or (mode == "mixed" and i % 3 == 0))
                 else "browse")
            params = {"message": q, "mode": m}
        else:
            params = None  # e.g. /catalog (works on the live service today, no params)
        t0 = time.monotonic()
        try:
            r = await client.get(f"{url}{endpoint}", params=params)
            ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ok = False
        lat.append((time.monotonic() - t0) * 1000)
        counts[0 if ok else 1] += 1
        i += 1


async def run_stage(url: str, endpoint: str, concurrency: int, duration: float, mode: str) -> dict:
    lat: list[float] = []
    counts = [0, 0]  # [ok, err]
    limits = httpx.Limits(max_connections=concurrency + 50,
                          max_keepalive_connections=concurrency + 50)
    deadline = time.monotonic() + duration
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
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
                    help="/sim/chat (this branch) or /catalog (works on the live service today)")
    args = ap.parse_args()

    stages = [int(s) for s in args.stages.split(",") if s.strip()]
    print(f"\n  GOOPHER load test → {args.url}{args.endpoint}   mode={args.mode}   {args.duration}s/stage")
    print("  (read-only, no LLM, no writes — safe to run against the live service)\n")
    print(f"  {'USERS':>7} {'REQS':>9} {'RPS':>9} {'p50ms':>8} {'p95ms':>8} "
          f"{'p99ms':>8} {'OK%':>7} {'ERR':>6}")
    print("  " + "-" * 70)
    for c in stages:
        r = await run_stage(args.url, args.endpoint, c, args.duration, args.mode)
        print(f"  {r['users']:>7} {r['total']:>9} {r['rps']:>9.0f} {r['p50']:>8.0f} "
              f"{r['p95']:>8.0f} {r['p99']:>8.0f} {r['ok_pct']:>6.1f}% {r['err']:>6}")
    print("\n  ↑ flat latency + rising RPS as users climb = Cloud Run scaling out.")
    print("  Watch instances grow in: Cloud Run → goopher-api → METRICS → Container instances.\n")


if __name__ == "__main__":
    asyncio.run(main())
