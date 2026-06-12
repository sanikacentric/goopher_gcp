#!/usr/bin/env python3
"""
GOOPHER — high-volume load generator (prove Cloud Run autoscaling at scale).

Drives concurrent "conversations" against the deployed service and prints a live
table per ramp stage. Three ways to run:

  1) DEFAULT — /sim/chat (read-only, NO LLM): isolates the APP's horizontal scaling.
       python scale/loadtest.py --stages 50,200,500 --duration 12

  2) HYBRID (RECOMMENDED for a realistic high-volume demo) — ONE run that mixes the
     real deterministic path with the real LLM path, just like production traffic:
     ~90% cheap deterministic (browse/status/checkout) + ~10% Gemini reasoning.
       python scale/loadtest.py --mix 10 --stages 50,150,300 --duration 15 \
           --email demo@goopher.app --password "<MASTER_PASSWORD>"
     (raise the rate limit first — see SCALE-CHEATSHEET.md.)

  3) Pure REAL-LLM — every request hits the orchestrator → Gemini (small only):
       python scale/loadtest.py --endpoint /chat --stages 5,10,20 ...

NOTHING here mutates data (product QUESTIONS only). The HYBRID run reports the
deterministic and LLM slices SEPARATELY so you see the hybrid behaviour in one shot.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles choke on arrows
except Exception:  # noqa: BLE001
    pass

try:
    import httpx
except ImportError:  # pragma: no cover
    raise SystemExit("Install httpx first:  pip install httpx")

DEFAULT_URL = "https://goopher-api-7vnucwimtq-uc.a.run.app"
QUERIES = ["oreo cookies", "potato chips", "soccer ball", "lego", "soda",
           "dress", "peanuts", "play-doh", "crackers", "nerf"]


def _pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, int(round((p / 100) * (len(s) - 1))))
    return s[k]


async def _worker(client, url, endpoint, mode, mix, pure_llm, deadline, st, idx):
    """st = {det:[ms], llm:[ms], c_det:[ok,err], c_llm:[ok,err]}"""
    i = idx
    while time.monotonic() < deadline:
        q = QUERIES[i % len(QUERIES)]
        # Decide this request's path.
        if pure_llm:
            use_llm = True
        elif mix > 0:
            use_llm = (i % 100) < mix          # mix% of requests use the real LLM
        else:
            use_llm = False
        t0 = time.monotonic()
        try:
            if use_llm:
                # REAL orchestrator → Gemini. Product question → nothing purchased.
                r = await client.post(f"{url}/chat", json={
                    "message": f"do you have {q}?", "session_id": f"load-{idx}",
                    "channel": "web"})
            elif endpoint == "/catalog":
                r = await client.get(f"{url}/catalog")
            else:
                m = ("order_status" if (mode == "order_status"
                     or (mode == "mixed" and i % 3 == 0)) else "browse")
                r = await client.get(f"{url}/sim/chat", params={"message": q, "mode": m})
            ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ok = False
        dt = (time.monotonic() - t0) * 1000
        if use_llm:
            st["llm"].append(dt); st["c_llm"][0 if ok else 1] += 1
        else:
            st["det"].append(dt); st["c_det"][0 if ok else 1] += 1
        i += 1


async def _login(url, email, password):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{url}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


async def run_stage(url, endpoint, concurrency, duration, mode, mix, pure_llm, token):
    st = {"det": [], "llm": [], "c_det": [0, 0], "c_llm": [0, 0]}
    limits = httpx.Limits(max_connections=concurrency + 50,
                          max_keepalive_connections=concurrency + 50)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    deadline = time.monotonic() + duration
    async with httpx.AsyncClient(timeout=90, limits=limits, headers=headers) as client:
        await asyncio.gather(*[
            _worker(client, url, endpoint, mode, mix, pure_llm, deadline, st, i)
            for i in range(concurrency)])
    det_ok, det_err = st["c_det"]; llm_ok, llm_err = st["c_llm"]
    total = det_ok + det_err + llm_ok + llm_err
    ok = det_ok + llm_ok
    return {
        "users": concurrency, "total": total, "rps": total / duration if duration else 0,
        "ok_pct": (ok / total * 100) if total else 0,
        "det_reqs": det_ok + det_err, "det_p95": _pct(st["det"], 95),
        "llm_reqs": llm_ok + llm_err, "llm_p95": _pct(st["llm"], 95),
        "err": det_err + llm_err,
    }


async def main():
    ap = argparse.ArgumentParser(description="GOOPHER high-volume load generator")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--stages", default="50,200,500")
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--mode", default="mixed", choices=["browse", "order_status", "mixed"])
    ap.add_argument("--endpoint", default="/sim/chat",
                    help="/sim/chat or /catalog (no-LLM), or /chat (pure REAL LLM)")
    ap.add_argument("--mix", type=int, default=0,
                    help="HYBRID: %% of requests that hit the REAL LLM /chat path "
                         "(rest are deterministic /sim/chat). e.g. --mix 10. Needs --password.")
    ap.add_argument("--email", default="demo@goopher.app")
    ap.add_argument("--password", default="")
    args = ap.parse_args()

    stages = [int(s) for s in args.stages.split(",") if s.strip()]
    pure_llm = args.endpoint == "/chat" and args.mix == 0
    needs_login = pure_llm or args.mix > 0
    token = None
    if needs_login:
        if not args.password:
            raise SystemExit("--password is required when LLM requests are involved "
                             "(--mix > 0 or --endpoint /chat).")
        token = await _login(args.url, args.email, args.password)
        print("  ✅ logged in — REAL Gemini calls included (product questions only; "
              "nothing purchased).")

    if args.mix > 0:
        label = f"HYBRID — {100 - args.mix}% deterministic + {args.mix}% REAL LLM (like production)"
    elif pure_llm:
        label = "PURE REAL LLM (/chat)"
    else:
        label = f"{args.endpoint} (no-LLM)"
    print(f"\n  GOOPHER load test → {args.url}   {label}   {args.duration}s/stage\n")
    print(f"  {'USERS':>7} {'TOTAL':>8} {'RPS':>7} {'OK%':>7} "
          f"{'DET-p95':>9} {'LLM-p95':>9} {'LLM-reqs':>9}")
    print("  " + "-" * 64)
    for c in stages:
        r = await run_stage(args.url, args.endpoint, c, args.duration, args.mode,
                            args.mix, pure_llm, token)
        print(f"  {r['users']:>7} {r['total']:>8} {r['rps']:>7.0f} {r['ok_pct']:>6.1f}% "
              f"{r['det_p95']:>8.0f}m {r['llm_p95']:>8.0f}m {r['llm_reqs']:>9}")
    print("\n  Read it like production: the DETERMINISTIC majority stays fast and scales")
    print("  cheaply; the LLM slice is small + heavier (that's why we keep it off the hot")
    print("  path). Watch Cloud Run → METRICS → Container instance count step up.\n")


if __name__ == "__main__":
    asyncio.run(main())
