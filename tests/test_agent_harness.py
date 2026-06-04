"""
Tests for the COMMON AgentHarness (scaffolding) shared by all GOOPHER agents.

The lifecycle (ready → session → run-loop → collect) is exercised with a FAKE ADK
runner, so no google packages or network are needed for the pure-Python parts.
The event-collection test needs google.genai (the harness builds a Content), so
it's skipped where that package is absent (CI), matching the rest of the suite.
"""
import pytest

from backend.app.agents.harness import AgentHarness, AgentRunResult


# --- AgentRunResult.text ordering ----------------------------------------- #
def test_result_text_prefers_final_then_last_then_transcript():
    assert AgentRunResult(ok=True, final_text="F", last_text="L", transcript="T").text == "F"
    assert AgentRunResult(ok=True, last_text="L", transcript="T").text == "L"
    assert AgentRunResult(ok=True, transcript="T").text == "T"
    assert AgentRunResult(ok=True).text == ""


# --- Graceful degradation when the agent can't be built ------------------- #
def test_harness_unavailable_when_build_fails():
    def boom():
        raise ImportError("no adk here")

    h = AgentHarness("x", "app", build_agent=boom)
    assert h.ready() is False
    res = h.run(user_id="u", session_id="s", prompt="hi")
    assert res.ok is False
    assert res.steps == ["build"]          # never got past build
    assert res.error


def test_harness_no_builder_and_no_runner_is_unavailable():
    h = AgentHarness("x", "app")           # neither build_agent nor runner
    assert h.ready() is False


# --- Run loop collects text / tool-calls / observations ------------------- #
class _Part:
    def __init__(self, text):
        self.text = text


class _Content:
    def __init__(self, text):
        self.parts = [_Part(text)]


class _FC:
    def __init__(self, name):
        self.name = name


class _FR:
    def __init__(self, name, response):
        self.name = name
        self.response = response


class _Event:
    def __init__(self, text, calls=(), responses=(), final=False):
        self.content = _Content(text)
        self._calls = list(calls)
        self._responses = list(responses)
        self._final = final

    def get_function_calls(self):
        return self._calls

    def get_function_responses(self):
        return self._responses

    def is_final_response(self):
        return self._final


class _FakeSessions:
    async def create_session(self, **kwargs):
        return None


class _FakeRunner:
    session_service = _FakeSessions()

    def __init__(self, events=None, raises=False):
        self._events = events or []
        self._raises = raises

    def run(self, **kwargs):
        if self._raises:
            raise RuntimeError("boom")
        for e in self._events:
            yield e


def test_harness_collects_events():
    pytest.importorskip("google.genai")   # harness builds a genai Content
    runner = _FakeRunner(events=[
        _Event("thinking…", calls=[_FC("search_inventory")]),
        _Event("", responses=[_FR("search_inventory", {"items": 2})]),
        _Event("Here is my pick.", final=True),
    ])
    h = AgentHarness("x", "app", runner=runner)
    res = h.run(user_id="u", session_id="s", prompt="hi")
    assert res.ok is True
    assert res.final_text == "Here is my pick."
    assert res.last_text == "Here is my pick."
    assert "thinking" in res.transcript and "Here is my pick." in res.transcript
    assert res.used_tools == ["search_inventory"]
    assert res.observations == [{"tool": "search_inventory", "result": {"items": 2}}]
    assert res.attempts == 1


def test_harness_retries_then_reports_failure():
    pytest.importorskip("google.genai")
    h = AgentHarness("x", "app", runner=_FakeRunner(raises=True))
    res = h.run(user_id="u", session_id="s", prompt="hi", retries=2)
    assert res.ok is False
    assert res.attempts == 2
    assert "boom" in res.error
