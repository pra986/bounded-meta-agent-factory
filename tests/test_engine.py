"""Pytest suite for BoundedMetaAgentFactory safety and execution bounds."""

from __future__ import annotations

from typing import Any

from meta_factory.engine import APPROVED_READ_ONLY_TOOLS, BoundedMetaAgentFactory
from meta_factory.models import AgentSpec, ChildEvalResult


def _valid_runner(
    spec: AgentSpec,
    task_input: dict[str, Any],
    revision: int,
) -> tuple[dict[str, Any], int]:
    return (
        {
            "spec_id": spec.spec_id,
            "revision": revision,
            "echo": task_input.get("query", ""),
        },
        300,
    )


def _heavy_token_runner(
    spec: AgentSpec,
    task_input: dict[str, Any],
    revision: int,
) -> tuple[dict[str, Any], int]:
    return ({"status": "ok"}, spec.token_budget + 500)


def _always_retry_runner(
    spec: AgentSpec,
    task_input: dict[str, Any],
    revision: int,
) -> tuple[dict[str, Any], int]:
    return ({"needs_revision": True, "reason": "incomplete"}, 100)


def test_disallowed_tool_is_rejected() -> None:
    factory = BoundedMetaAgentFactory()
    factory.register_template("read_only_analyst", _valid_runner)

    spec = AgentSpec(
        spec_id="spec-bad-tool",
        name="UnsafeAgent",
        role="Analyst",
        goal="Attempt shell tool",
        template_id="read_only_analyst",
        allowed_tools=["read_file", "execute_shell"],
        token_budget=1000,
        recursion_depth=1,
        spawn_children=False,
        max_revisions=2,
    )

    validation = factory.validate_spec(spec)
    assert validation.approved is False
    assert any("execute_shell" in v for v in validation.violations)

    result = factory.run_child(spec, {"query": "audit"})
    assert isinstance(result, ChildEvalResult)
    assert result.status == "rejected"
    assert result.output is None


def test_recursive_spawning_beyond_depth_1_is_blocked() -> None:
    factory = BoundedMetaAgentFactory()
    factory.register_template("read_only_analyst", _valid_runner)

    depth_spec = AgentSpec(
        spec_id="spec-depth-2",
        name="NestedAgent",
        role="Spawner",
        goal="Spawn grandchild",
        template_id="read_only_analyst",
        allowed_tools=["read_file"],
        token_budget=1000,
        recursion_depth=2,
        spawn_children=False,
        max_revisions=2,
    )
    depth_result = factory.run_child(depth_spec, {"query": "nested"})
    assert depth_result.status == "rejected"

    spawn_spec = AgentSpec(
        spec_id="spec-spawn-true",
        name="ChildSpawner",
        role="Spawner",
        goal="Enable child spawning",
        template_id="read_only_analyst",
        allowed_tools=["read_file"],
        token_budget=1000,
        recursion_depth=1,
        spawn_children=True,
        max_revisions=2,
    )
    spawn_result = factory.run_child(spawn_spec, {"query": "nested"})
    assert spawn_result.status == "rejected"


def test_max_revision_budget_halts_execution() -> None:
    factory = BoundedMetaAgentFactory()
    factory.register_template("read_only_analyst", _always_retry_runner)

    spec = AgentSpec(
        spec_id="spec-revisions",
        name="RetryAgent",
        role="Analyst",
        goal="Exhaust revision budget",
        template_id="read_only_analyst",
        allowed_tools=["read_file"],
        token_budget=2000,
        recursion_depth=1,
        spawn_children=False,
        max_revisions=2,
    )

    result = factory.run_child(spec, {"query": "retry"})
    assert isinstance(result, ChildEvalResult)
    assert result.status in {"failed_revisions", "completed"}
    assert result.revisions_used <= spec.max_revisions


def test_token_budget_and_typed_result_delivery() -> None:
    factory = BoundedMetaAgentFactory()
    factory.register_template("read_only_analyst", _valid_runner)
    factory.register_template("heavy_analyst", _heavy_token_runner)

    valid_spec = AgentSpec(
        spec_id="spec-valid",
        name="CompliantAnalyst",
        role="Read-Only Analyst",
        goal="Deliver typed summary",
        template_id="read_only_analyst",
        allowed_tools=sorted(APPROVED_READ_ONLY_TOOLS)[:2],
        token_budget=1500,
        recursion_depth=1,
        spawn_children=False,
        max_revisions=2,
    )
    ok_result = factory.run_child(valid_spec, {"query": "metrics"})
    assert isinstance(ok_result, ChildEvalResult)
    assert ok_result.status == "completed"
    assert ok_result.output is not None
    assert ok_result.artifact_version == 1
    assert ok_result.spec_digest is not None

    over_budget_spec = AgentSpec(
        spec_id="spec-over-budget",
        name="HeavyAnalyst",
        role="Read-Only Analyst",
        goal="Exceed token budget",
        template_id="heavy_analyst",
        allowed_tools=["read_file"],
        token_budget=500,
        recursion_depth=1,
        spawn_children=False,
        max_revisions=2,
    )
    budget_result = factory.run_child(over_budget_spec, {"query": "heavy"})
    assert isinstance(budget_result, ChildEvalResult)
    assert budget_result.status == "failed_budget"
