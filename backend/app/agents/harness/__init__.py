"""
Agent harness (scaffolding) package — the COMMON runtime wrapper shared by ALL
GOOPHER agents (the orchestrator + its workers, and the ReAct shopping advisor).

Import the harness from here:

    from .harness import AgentHarness, AgentRunResult
"""
from .agent_harness import AgentHarness, AgentRunResult

__all__ = ["AgentHarness", "AgentRunResult"]
