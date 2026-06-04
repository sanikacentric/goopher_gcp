"""
Agent Skill Registry — the single source of truth for GOOPHER's agent skills.

An *agent skill* = a cohesive, named capability bundling:
  * an INSTRUCTION snippet (teaches the LLM when/how to use it), and
  * a set of callable TOOLS (get_tools()) that implement it.

Previously each agent imported its skill module directly and bound the tools
statically. This registry centralizes that: every skill is registered ONCE here
with metadata (name, title, description, read_only), and agents pull their skills
BY NAME from the registry. Benefits:
  * one source of truth + introspection (GET /skills lists them),
  * read-only skills are flagged, so read-only agents (the ReAct advisor) can
    assert they never pick a transactional skill,
  * the orchestrator could later attach skills dynamically per turn.

Behavior is unchanged — the registry wraps the SAME skill modules and returns the
SAME tools/instructions; it just makes the wiring explicit and inspectable.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import checkout_skill, inventory_skill, order_mgmt_skill, order_skill


@dataclass(frozen=True)
class AgentSkill:
    """One registered agent skill. `module` is the underlying skill module that
    owns the INSTRUCTION text and the get_tools() callable."""
    name: str                 # stable key used to look the skill up (e.g. "inventory")
    title: str                # human-friendly label for the dev portal / docs
    description: str          # one-line summary of the capability
    read_only: bool           # True = no writes/transactions (safe for advisors)
    module: object            # the skill module (inventory_skill, etc.)

    @property
    def instruction(self) -> str:
        """The skill's LLM instruction snippet."""
        return self.module.INSTRUCTION

    def get_tools(self) -> list:
        """The skill's callable tools (bound onto an agent)."""
        return self.module.get_tools()

    def tool_names(self) -> list[str]:
        """The tool function names — for introspection / the /skills endpoint."""
        return [getattr(t, "__name__", str(t)) for t in self.get_tools()]


# --------------------------------------------------------------------------- #
# THE REGISTRY — every agent skill registered exactly once.
# --------------------------------------------------------------------------- #
AGENT_SKILL_REGISTRY: dict[str, AgentSkill] = {
    "inventory": AgentSkill(
        name="inventory",
        title="Inventory & Discovery",
        description="Search products and check price/stock across Clothing, Food, and Toys.",
        read_only=True,
        module=inventory_skill,
    ),
    "order": AgentSkill(
        name="order",
        title="Order Tracking",
        description="Look up order status/tracking, list a customer's orders, and bulk status.",
        read_only=True,
        module=order_skill,
    ),
    "checkout": AgentSkill(
        name="checkout",
        title="Checkout & Place Order",
        description="Add to cart, run the (simulated) payment, and place single or bulk orders.",
        read_only=False,
        module=checkout_skill,
    ),
    "fulfillment": AgentSkill(
        name="fulfillment",
        title="Order Fulfillment Pipeline",
        description="Post-payment pipeline: validate → inventory check → ORDER_PLACED → ship → deliver → invoice.",
        read_only=False,
        module=order_mgmt_skill,
    ),
}


# --------------------------------------------------------------------------- #
# Lookup / composition helpers — how agents PICK their skills.
# --------------------------------------------------------------------------- #
def get_skill(name: str) -> AgentSkill:
    """Return the registered skill by name. Raises KeyError if unknown."""
    try:
        return AGENT_SKILL_REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(
            f"Unknown agent skill '{name}'. Registered: {sorted(AGENT_SKILL_REGISTRY)}"
        ) from exc


def list_skills() -> list[AgentSkill]:
    """All registered skills (stable order) — for introspection."""
    return list(AGENT_SKILL_REGISTRY.values())


def get_tools(*names: str) -> list:
    """Compose the tools of one or more skills, in the order given.

    Example: get_tools("inventory", "order) -> all read-only browse+track tools.
    """
    tools: list = []
    for n in names:
        tools.extend(get_skill(n).get_tools())
    return tools


def read_only_skill_names() -> list[str]:
    """Names of skills that perform NO writes/transactions — the only skills a
    read-only agent (e.g. the ReAct shopping advisor) may pick."""
    return [s.name for s in list_skills() if s.read_only]


def describe() -> list[dict]:
    """Registry as plain dicts for the GET /skills endpoint / dev portal."""
    return [
        {
            "name": s.name,
            "title": s.title,
            "description": s.description,
            "read_only": s.read_only,
            "tools": s.tool_names(),
        }
        for s in list_skills()
    ]
