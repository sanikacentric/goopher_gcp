# GOOPHER Evals

Behavioral evaluation of the unified conversational agent.

## What it measures
Each case in [`eval_dataset.json`](eval_dataset.json) is one shopper turn with
labeled expectations. The harness scores four dimensions:

| Check | Meaning |
|-------|---------|
| `tool_match` | Agent invoked the correct backend (MCP) tool |
| `grounded` | Reply contains expected facts from the real data (no hallucination) |
| `language_match` | Reply is in the expected language (multi-lingual subagent) |
| `channel_safe` | Phone replies contain no markdown/URLs (multi-channel subagent) |

## Run
```bash
# Offline (deterministic fallback engine, CI-friendly)
python evals/run_evals.py

# Live (evaluates the real Gemini + ADK path)
export GOOGLE_API_KEY=...        # Windows: set GOOGLE_API_KEY=...
python evals/run_evals.py
```

The script exits non-zero if the aggregate pass rate falls below `THRESHOLD`
(80%), so it gates the CI/CD pipeline (see `.github/workflows/deploy.yml`).

## Extending
Add new cases to `eval_dataset.json`. Useful additions: adversarial prompts
(off-topic, prompt injection), more languages, and out-of-stock edge cases.
