"""
GOOPHER evaluation harness (Requirement T8: CREATE EVALS).

Runs the unified agent over a labeled dataset and scores each turn on:
  * tool_match     — did the agent invoke the expected backend tool?
  * grounded       — does the reply contain at least one expected fact token?
  * language_match — did it answer in the expected language?
  * channel_safe   — for phone, is the reply free of markdown/URLs?

Runs offline against the deterministic fallback engine by default (no API key),
so it's CI-friendly. With GOOGLE_API_KEY set it evaluates the live Gemini path.

Usage:
    python evals/run_evals.py
Exit code is non-zero if the aggregate score drops below THRESHOLD, so it can
gate a CI/CD pipeline.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force hermetic defaults unless the operator opted into the live LLM path.
os.environ.setdefault("DB_BACKEND", "sqlite")
os.environ.setdefault("ENABLE_TRACING", "false")

from backend.app.agents.orchestrator import AgentService  # noqa: E402
from backend.app.models.schemas import ChatRequest  # noqa: E402

DATASET = Path(__file__).resolve().parent / "eval_dataset.json"
THRESHOLD = 0.80  # aggregate pass rate required for CI to pass
MARKDOWN_RE = re.compile(r"[*_`#]|\]\(|https?://")


def grade_case(svc: AgentService, case: dict) -> dict:
    resp = svc.run_turn(
        ChatRequest(
            message=case["message"],
            session_id=f"eval-{case['id']}",
            channel=case.get("channel", "web"),
        ),
        customer_id=case["customer_id"],
    )
    checks = {}

    # tool selection
    expected_tools = set(case.get("expect_tools", []))
    checks["tool_match"] = bool(expected_tools & set(resp.used_tools)) if expected_tools else True

    # groundedness
    needles = case.get("expect_contains_any", [])
    checks["grounded"] = any(n.lower() in resp.reply.lower() for n in needles) if needles else True

    # language
    exp_lang = case.get("expect_language")
    checks["language_match"] = (resp.language == exp_lang) if exp_lang else True

    # channel safety
    if case.get("expect_no_markdown"):
        checks["channel_safe"] = not bool(MARKDOWN_RE.search(resp.reply))
    else:
        checks["channel_safe"] = True

    passed = all(checks.values())
    return {"id": case["id"], "passed": passed, "checks": checks,
            "used_tools": resp.used_tools, "reply": resp.reply[:160]}


def main() -> int:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    svc = AgentService()
    results = [grade_case(svc, c) for c in data["cases"]]

    n = len(results)
    n_pass = sum(1 for r in results if r["passed"])
    score = n_pass / n if n else 0.0

    print("=" * 72)
    print(f"GOOPHER EVALS  ({'LIVE Gemini' if os.environ.get('GOOGLE_API_KEY') else 'offline fallback'})")
    print("=" * 72)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        failed = [k for k, v in r["checks"].items() if not v]
        detail = "" if r["passed"] else f"  -> failed: {', '.join(failed)}"
        print(f"[{mark}] {r['id']:24s} tools={r['used_tools']}{detail}")
    print("-" * 72)
    print(f"Aggregate: {n_pass}/{n} = {score:.0%}  (threshold {THRESHOLD:.0%})")

    if score < THRESHOLD:
        print("RESULT: BELOW THRESHOLD [FAIL]")
        return 1
    print("RESULT: PASS [OK]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
