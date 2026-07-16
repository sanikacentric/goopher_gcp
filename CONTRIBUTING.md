# Contributing to GOOPHER

Thanks for your interest in GOOPHER! Contributions are welcome.

## Getting set up

```bash
git clone https://github.com/sanikacentric/goopher_gcp.git
cd goopher_gcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in what you need — see below
uvicorn backend.app.main:app --reload --port 8080
```

GOOPHER runs with **zero secrets** out of the box:

| Concern | Default with no config |
|---|---|
| Database | SQLite (`DB_BACKEND=sqlite`), auto-created |
| LLM | Falls back to a deterministic path; set a key for real Gemini |
| Order email | **Simulated** — logged and shown in the reply, nothing sent |
| Login | Fail-closed: set `MASTER_PASSWORD` in `.env` to log in |

To use real Gemini, either set `GOOGLE_API_KEY` (AI Studio) **or** use Vertex AI
(`USE_VERTEXAI=true` + `gcloud auth application-default login`).

The Chrome extension points at `http://localhost:8080` by default — see
[`extension/config.js`](extension/config.js). Load it via
`chrome://extensions` → Developer mode → **Load unpacked** → select `extension/`.

## Before you open a PR

```bash
python -m pytest tests/ -q      # unit tests — all must pass
python evals/run_evals.py       # agent-quality evals — must score >= 0.80
```

Both run in CI. The deploy job is skipped automatically on forks (no cloud
secrets), so CI still passes on your PR.

## Ground rules

- **Never commit secrets.** `.env`, `*.db`, and `*-key.json` are gitignored —
  keep it that way. Use `.env.example` to document a *new* variable, with an
  empty value.
- **No personal data.** Use `example.com` addresses and `<your-project-id>`
  style placeholders in code, tests, and docs.
- **Match the surrounding style.** The codebase favors small, documented
  functions and explains *why* in comments, not *what*.
- **Add a test** for behavior changes, and an eval case in
  [`evals/eval_dataset.json`](evals/eval_dataset.json) for agent-behavior changes.

## Architecture orientation

Start with [`ARCHITECTURE.md`](ARCHITECTURE.md), then
[`backend/app/agents/orchestrator.py`](backend/app/agents/orchestrator.py) — the
root ADK agent that routes to the worker agents. The guiding principle is
**"the LLM orchestrates, code transacts"**: the model decides *what* to do, but
money-moving steps run through deterministic code with an explicit confirm gate.

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
