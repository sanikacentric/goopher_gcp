# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities.

Instead, use GitHub's private reporting:
**Security → Advisories → Report a vulnerability** on this repository.

Include what you found, how to reproduce it, and the impact you expect. You'll
get an acknowledgement within a few days.

## Scope and status

GOOPHER is a **demonstration project**, not a production retail system. Please
keep that in mind when assessing severity:

- **Payments are simulated.** `process_payment` in
  [`backend/app/tools/checkout_tool.py`](backend/app/tools/checkout_tool.py)
  always succeeds and moves no money. There is no PSP integration.
- **The catalog is synthetic.** No real customer, order, or payment data exists
  in this repo.
- **Auth is a single-user lockdown**, not a multi-tenant identity system: an
  email allowlist (`ALLOWED_EMAILS`) plus one shared `MASTER_PASSWORD`.

## If you deploy this yourself

The defaults are safe, but they are *defaults*. Before exposing an instance:

- **Set `MASTER_PASSWORD`** to a strong secret via env / Secret Manager. If it's
  left at the `CHANGE_ME_set_via_env` sentinel the service **rejects every
  login** (fail-closed by design) — don't work around that by hardcoding it.
- **Set `JWT_SECRET`** to a long random string. The `change-me-in-production`
  default must not survive into a deployed environment.
- **Restrict `ALLOWED_EMAILS`** to the accounts you actually want.
- **Never commit `.env`.** It is gitignored; keep real keys in GitHub Actions
  secrets or Secret Manager. If you ever leak a key, **rotate it first**, then
  clean up the history.
- **Prefer Vertex AI over an API key** (`USE_VERTEXAI=true`), so the service
  authenticates via its service account and there is no long-lived key to leak.

## Known non-issues

These are intentional and don't need a report:

- `/sim/*` endpoints are exempt from the rate limiter — they exist purely for
  load testing, are read-only, and invoke no LLM. They're gated behind
  `SCALE_SIM_ENABLED`; set it to `false` to remove them.
- Order confirmation email runs in **simulated mode** with no transport
  configured, which logs the message rather than sending it.
