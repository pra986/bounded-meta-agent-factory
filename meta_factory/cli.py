"""Runnable CLI demo entrypoint for the Bounded Meta-Agent Factory."""

from __future__ import annotations

import argparse
import json
from typing import Any

from meta_factory.engine import BoundedMetaAgentFactory
from meta_factory.models import AgentSpec


def _demo_analyst_runner(
    spec: AgentSpec,
    task_input: dict[str, Any],
    revision: int,
) -> tuple[dict[str, Any], int]:
    """Deterministic read-only child runner for CLI demonstrations."""
    return (
        {
            "summary": f"Completed '{spec.goal}' on revision {revision}",
            "tools_available": list(spec.allowed_tools),
            "query": task_input.get("query", "default_audit"),
        },
        250,
    )


def build_demo_factory() -> BoundedMetaAgentFactory:
    factory = BoundedMetaAgentFactory()
    factory.register_template("read_only_analyst", _demo_analyst_runner)
    return factory


def run_demo(scenario: str = "all") -> list[dict[str, Any]]:
    factory = build_demo_factory()
    scenarios: dict[str, AgentSpec] = {
        "valid": AgentSpec(
            spec_id="spec-valid-001",
            name="PolicyAuditor",
            role="Read-Only Compliance Analyst",
            goal="Summarize approved repository metrics",
            template_id="read_only_analyst",
            allowed_tools=["read_file", "query_metrics"],
            token_budget=1500,
            recursion_depth=1,
            spawn_children=False,
            max_revisions=2,
        ),
        "disallowed_tool": AgentSpec(
            spec_id="spec-blocked-tool-002",
            name="UnsafeWriter",
            role="Mutating Agent",
            goal="Attempt unapproved shell execution",
            template_id="read_only_analyst",
            allowed_tools=["read_file", "execute_shell"],
            token_budget=1500,
            recursion_depth=1,
            spawn_children=False,
            max_revisions=2,
        ),
        "recursive_spawn": AgentSpec(
            spec_id="spec-blocked-depth-003",
            name="RecursiveSpawner",
            role="Nested Orchestrator",
            goal="Attempt depth-2 child spawning",
            template_id="read_only_analyst",
            allowed_tools=["read_file"],
            token_budget=1500,
            recursion_depth=2,
            spawn_children=True,
            max_revisions=2,
        ),
    }

    selected = scenarios.items() if scenario == "all" else [(scenario, scenarios[scenario])]
    results: list[dict[str, Any]] = []
    for label, spec in selected:
        eval_result = factory.run_child(spec, {"query": f"demo:{label}"})
        results.append({"scenario": label, "result": eval_result.model_dump()})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="meta-factory-demo",
        description="Run bounded meta-agent factory policy and execution demos.",
    )
    parser.add_argument(
        "--scenario",
        choices=["all", "valid", "disallowed_tool", "recursive_spawn"],
        default="all",
        help="Demo scenario to execute.",
    )
    args = parser.parse_args()
    output = run_demo(args.scenario)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
