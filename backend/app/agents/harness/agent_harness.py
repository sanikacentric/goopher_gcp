"""
AgentHarness — the COMMON agent scaffolding for GOOPHER.

Every ADK agent in GOOPHER needs the same runtime "scaffolding" around it to go
from *configured* to *reliably runnable*:

    build the agent → create a Runner → ensure the session exists →
    stream the turn → collect (text / tool-calls / observations) →
    apply resilience (retry, graceful failure) → return a STRUCTURED result.

That boilerplate used to be copy-pasted inside the orchestrator (`_generate_adk`)
AND the shopping advisor. This module extracts it ONCE so it is shared by ALL
agents:

    • the production orchestrator + its 4 worker sub-agents  (app "goopher")
    • the read-only ReAct shopping advisor                   (app "goopher-advisor")

…and any future agent just constructs an `AgentHarness(build_agent=…)` and calls
`.run(...)`. Behavior is identical to the previous inline code — this is pure
scaffolding/refactor, not a behavior change.

Design notes:
  * google-adk / google-genai are imported LAZILY, so importing this module never
    requires the heavy packages (CI runs without them).
  * `ready()` builds the Runner once and degrades gracefully (returns False, never
    raises) when ADK/Gemini isn't available — the caller then uses its fallback.
  * `run()` returns an `AgentRunResult` carrying everything any caller needs:
    `final_text` (the is_final_response text), `last_text` (last non-empty text),
    `transcript` (ALL text joined — for ReAct parsing), `used_tools`,
    `observations` (tool results), plus `steps`/`attempts`/`error` for telemetry.
  * `retries` re-runs the whole turn on a transient error. Default 1 (no retry).
    Use >1 ONLY for idempotent/read-only agents (e.g. the advisor) — never for a
    transactional turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ...observability.telemetry import log_event, span


@dataclass
class AgentRunResult:
    """Everything a caller needs from one agent turn — the structured output of
    the harness. `ok=False` means the harness couldn't run (no ADK) or every
    attempt errored; inspect `error`/`steps`."""
    ok: bool
    final_text: str = ""                       # text of the is_final_response event
    last_text: str = ""                        # last non-empty text from any event
    transcript: str = ""                       # ALL text events joined with "\n"
    used_tools: list = field(default_factory=list)
    observations: list = field(default_factory=list)   # [{tool, result}, ...]
    steps: list = field(default_factory=list)          # lifecycle breadcrumbs
    attempts: int = 0
    error: str = ""

    @property
    def text(self) -> str:
        """Best single reply: the final response, else the last text, else the
        whole transcript (stripped)."""
        return (self.final_text or self.last_text or self.transcript).strip()


class AgentHarness:
    """Reusable scaffolding that runs ONE ADK agent (which may itself orchestrate
    sub-agents) through a consistent, observable, resilient lifecycle."""

    def __init__(
        self,
        name: str,
        app_name: str,
        build_agent: Optional[Callable[[], object]] = None,
        runner: object = None,
    ):
        """
        Args:
          name:        label for telemetry/spans (e.g. "orchestrator", "advisor").
          app_name:    ADK app name (the Runner's namespace).
          build_agent: zero-arg callable returning the ADK agent to run. Called
                       lazily on first `ready()`. (Either this or `runner`.)
          runner:      an already-built ADK Runner to wrap instead of building one.
        """
        self.name = name
        self.app_name = app_name
        self._build = build_agent
        self._runner = runner
        self._ready = runner is not None
        self._sessions: set[str] = set()
        self.last_error = ""

    # -- lifecycle ---------------------------------------------------------- #
    def ready(self) -> bool:
        """Build the Runner once. Returns True if the agent can be run; False
        (never raises) if ADK/Gemini isn't available — caller uses its fallback."""
        if self._ready:
            return True
        if self._build is None:
            return False
        try:
            from google.adk.runners import InMemoryRunner

            self._runner = InMemoryRunner(agent=self._build(), app_name=self.app_name)
            self._ready = True
            log_event("harness_init", harness=self.name, app=self.app_name)
            return True
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash
            self.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            log_event("harness_unavailable", harness=self.name, reason=str(exc))
            return False

    @property
    def runner(self):
        """The underlying ADK Runner (None until ready())."""
        return self._runner

    def _ensure_session(self, user_id: str, session_id: str) -> None:
        """Create the ADK session once per session_id (idempotent)."""
        if session_id in self._sessions:
            return
        import asyncio

        try:
            asyncio.run(
                self._runner.session_service.create_session(
                    app_name=self.app_name, user_id=user_id, session_id=session_id
                )
            )
        except Exception as exc:  # already exists / transient
            log_event("harness_session_skipped", harness=self.name, reason=str(exc))
        self._sessions.add(session_id)

    # -- run ---------------------------------------------------------------- #
    def run(self, *, user_id: str, session_id: str, prompt: str,
            retries: int = 1) -> AgentRunResult:
        """Run one turn and return a structured result. Never raises — failures
        come back as `ok=False`. `retries` > 1 re-runs the turn on a transient
        error (ONLY safe for idempotent/read-only agents)."""
        steps = ["build"]
        if not self.ready():
            return AgentRunResult(ok=False, steps=steps,
                                  error=self.last_error or "harness unavailable")

        from google.genai import types

        self._ensure_session(user_id, session_id)
        steps = steps + ["session"]
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        attempts = max(1, retries)
        last_err = ""
        for attempt in range(1, attempts + 1):
            used_tools: list = []
            transcript: list = []
            observations: list = []
            final_text = ""
            last_text = ""
            try:
                with span(f"harness.{self.name}.run"):
                    for event in self._runner.run(
                        user_id=user_id, session_id=session_id, new_message=content
                    ):
                        if getattr(event, "get_function_calls", None):
                            for fc in event.get_function_calls() or []:
                                used_tools.append(fc.name)
                        if getattr(event, "get_function_responses", None):
                            for fr in event.get_function_responses() or []:
                                observations.append({
                                    "tool": getattr(fr, "name", "?"),
                                    "result": getattr(fr, "response", None),
                                })
                        if event.content and event.content.parts:
                            txt = "".join(p.text or "" for p in event.content.parts)
                            if txt.strip():
                                transcript.append(txt)
                                last_text = txt
                            if getattr(event, "is_final_response", lambda: False)():
                                final_text = txt
                return AgentRunResult(
                    ok=True,
                    final_text=final_text,
                    last_text=last_text,
                    transcript="\n".join(transcript).strip(),
                    used_tools=used_tools,
                    observations=observations,
                    steps=steps + [f"run#{attempt}"],
                    attempts=attempt,
                )
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {str(exc)[:200]}"
                log_event("harness_run_failed", harness=self.name,
                          attempt=attempt, reason=str(exc))
                steps = steps + [f"error#{attempt}"]

        return AgentRunResult(ok=False, steps=steps, attempts=attempts, error=last_err)
