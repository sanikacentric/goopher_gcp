"""
Tests for the Agent Skill Registry — the single source of truth that agents pick
their skills from. Hermetic: exercises registry lookup/composition + the /skills
endpoint without any LLM/ADK.
"""
from backend.app.agents.skills import agent_skill_registry as reg
from backend.app.agents.skills import checkout_skill, inventory_skill
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_registry_has_expected_skills():
    assert set(reg.AGENT_SKILL_REGISTRY) == {"inventory", "order", "checkout", "fulfillment"}


def test_get_skill_wraps_the_same_module():
    inv = reg.get_skill("inventory")
    assert inv.instruction == inventory_skill.INSTRUCTION         # same instruction
    assert inv.get_tools() == inventory_skill.get_tools()         # same tools
    assert "search_inventory" in inv.tool_names()


def test_get_skill_unknown_raises():
    try:
        reg.get_skill("nope")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_read_only_flags_are_correct():
    assert reg.get_skill("inventory").read_only is True
    assert reg.get_skill("order").read_only is True
    assert reg.get_skill("checkout").read_only is False          # transactional
    assert reg.get_skill("fulfillment").read_only is False       # transactional
    assert reg.read_only_skill_names() == ["inventory", "order"]


def test_get_tools_composes_in_order():
    composed = reg.get_tools("inventory", "order")
    assert composed == inventory_skill.get_tools() + reg.get_skill("order").get_tools()


def test_advisor_only_picks_read_only_skills_disjoint_from_checkout():
    # The read-only skills the advisor uses must share NO tool with checkout.
    advisor_tools = set(reg.get_tools(*reg.read_only_skill_names()))
    assert advisor_tools.isdisjoint(set(checkout_skill.get_tools()))


def test_describe_shape():
    rows = reg.describe()
    assert {r["name"] for r in rows} == {"inventory", "order", "checkout", "fulfillment"}
    inv = next(r for r in rows if r["name"] == "inventory")
    assert inv["read_only"] is True and "search_inventory" in inv["tools"]
    assert inv["title"] and inv["description"]


def test_skills_endpoint_is_public_and_lists_registry():
    r = client.get("/skills")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()["skills"]}
    assert names == {"inventory", "order", "checkout", "fulfillment"}
