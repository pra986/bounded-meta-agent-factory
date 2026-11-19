from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from meta_factory.models import AgentSpec, ChildEvalResult, PolicyValidationResult

APPROVED_READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "search_docs",
        "query_metrics",
        "list_artifacts",
        "inspect_schema",
    }
)

MAX_RECURSION_DEPTH: int = 1
DEFAULT_MAX_REVISIONS: int = 2
DEFAULT_MAX_TOKEN_BUDGET: int = 8000


@dataclass(frozen=True)
class ArtifactRecord:
    """Immutable versioned artifact snapshot stored in the factory registry."""

    version: int
    spec_id: str
    spec_digest: str
    status: str
    output: dict[str, Any] | None
    tokens_used: int
    revisions_used: int


class ArtifactRegistry:
    """Versioned registry for declarative child specs and evaluation outputs."""

    def __init__(self) -> None:
        self._records: list[ArtifactRecord] = []

    def register(
        self,
        spec: AgentSpec,
        status: str,
        output: dict[str, Any] | None,
        tokens_used: int,
        revisions_used: int,
    ) -> ArtifactRecord:
        digest = hashlib.sha256(
            json.dumps(spec.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        record = ArtifactRecord(
            version=len(self._records) + 1,
            spec_id=spec.spec_id,
            spec_digest=digest,
            status=status,
            output=output,
            tokens_used=tokens_used,
            revisions_used=revisions_used,
        )
        self._records.append(record)
        return record

    def list_versions(self, spec_id: str | None = None) -> list[ArtifactRecord]:
        if spec_id is None:
            return list(self._records)
        return [r for r in self._records if r.spec_id == spec_id]


TemplateHandler = Callable[[AgentSpec, int, dict[str, Any]], tuple[bool, dict[str, Any], int]]


def _default_read_only_analyst(
    spec: AgentSpec, revision: int, context: dict[str, Any]
) -> tuple[bool, dict[str, Any], int]:
    """Deterministic isolated template handler without raw exec/eval."""
    tokens_spent = int(context.get("tokens_per_attempt", 350))
    force_fail_revisions = bool(context.get("force_fail_revisions", False))
    passed = not force_fail_revisions and (
        revision >= int(context.get("pass_on_revision", 0))
    )
    payload = {
        "agent": spec.name,
        "role": spec.role,
        "goal": spec.goal,
        "revision": revision,
        "tools_bound": list(spec.allowed_tools),
        "summary": f"Completed bounded read-only analysis for '{spec.goal}'.",
    }
    return passed, payload, tokens_spent


class BoundedMetaAgentFactory:
    """Declarative meta-agent factory with strict safety & budget controls."""

    def __init__(
        self,
        max_recursion_depth: int = MAX_RECURSION_DEPTH,
        max_token_budget: int = DEFAULT_MAX_TOKEN_BUDGET,
        max_revisions: int = DEFAULT_MAX_REVISIONS,
        approved_tools: frozenset[str] = APPROVED_READ_ONLY_TOOLS,
    ) -> None:
        self.max_recursion_depth = min(max_recursion_depth, MAX_RECURSION_DEPTH)
        self.max_token_budget = max_token_budget
        self.max_revisions = min(max_revisions, DEFAULT_MAX_REVISIONS)
        self.approved_tools = approved_tools
        self.registry = ArtifactRegistry()
        self._templates: dict[str, TemplateHandler] = {
            "read_only_analyst": _default_read_only_analyst,
        }

    def register_template(self, template_id: str, handler: TemplateHandler) -> None:
        self._templates[template_id] = handler

    def validate_spec(
        self, spec: AgentSpec, current_depth: int = 0
    ) -> PolicyValidationResult:
        violations: list[str] = []
        effective_depth = current_depth + 1

        if current_depth >= self.max_recursion_depth:
            violations.append(
                f"Recursive spawning blocked: current_depth={current_depth} "
                f"cannot spawn beyond max_recursion_depth={self.max_recursion_depth}."
            )
        if spec.recursion_depth > self.max_recursion_depth:
            violations.append(
                f"Requested recursion_depth={spec.recursion_depth} exceeds "
                f"max_recursion_depth={self.max_recursion_depth}."
            )
        if spec.spawn_children and effective_depth >= self.max_recursion_depth:
            violations.append(
                "Child agents at depth 1 are forbidden from spawning grandchildren."
            )

        disallowed = [t for t in spec.allowed_tools if t not in self.approved_tools]
        if disallowed:
            violations.append(
                f"Disallowed tools requested: {disallowed}. "
                f"Approved read-only tools: {sorted(self.approved_tools)}."
            )

        if spec.token_budget > self.max_token_budget:
            violations.append(
                f"Requested token_budget={spec.token_budget} exceeds "
                f"max_token_budget={self.max_token_budget}."
            )
        if spec.max_revisions > self.max_revisions:
            violations.append(
                f"Requested max_revisions={spec.max_revisions} exceeds "
                f"bounded limit={self.max_revisions}."
            )
        if spec.template_id not in self._templates:
            violations.append(
                f"Unknown template_id='{spec.template_id}'. Raw exec/eval is prohibited."
            )

        sanitized = [t for t in spec.allowed_tools if t in self.approved_tools]
        return PolicyValidationResult(
            approved=len(violations) == 0,
            violations=violations,
            sanitized_tools=sanitized,
            effective_depth=effective_depth,
        )

    def run_child(
        self,
        spec: AgentSpec,
        current_depth: int = 0,
        context: dict[str, Any] | None = None,
    ) -> ChildEvalResult:
        ctx = context or {}
        validation = self.validate_spec(spec, current_depth=current_depth)
        if not validation.approved:
            error_msg = "; ".join(validation.violations)
            record = self.registry.register(
                spec=spec,
                status="rejected",
                output=None,
                tokens_used=0,
                revisions_used=0,
            )
            return ChildEvalResult(
                spec_id=spec.spec_id,
                status="rejected",
                output=None,
                tokens_used=0,
                revisions_used=0,
                artifact_version=record.version,
                spec_digest=record.spec_digest,
                error=error_msg,
            )

        handler = self._templates[spec.template_id]
        tokens_used = 0
        revisions_used = 0
        last_output: dict[str, Any] | None = None

        for attempt in range(spec.max_revisions + 1):
            passed, output, spent = handler(spec, attempt, ctx)
            if tokens_used + spent > spec.token_budget:
                error_msg = (
                    f"Token budget exceeded: {tokens_used + spent} > {spec.token_budget}."
                )
                record = self.registry.register(
                    spec=spec,
                    status="failed_budget",
                    output=last_output,
                    tokens_used=tokens_used,
                    revisions_used=revisions_used,
                )
                return ChildEvalResult(
                    spec_id=spec.spec_id,
                    status="failed_budget",
                    output=last_output,
                    tokens_used=tokens_used,
                    revisions_used=revisions_used,
                    artifact_version=record.version,
                    spec_digest=record.spec_digest,
                    error=error_msg,
                )

            tokens_used += spent
            last_output = output
            if passed:
                record = self.registry.register(
                    spec=spec,
                    status="completed",
                    output=output,
                    tokens_used=tokens_used,
                    revisions_used=revisions_used,
                )
                return ChildEvalResult(
                    spec_id=spec.spec_id,
                    status="completed",
                    output=output,
                    tokens_used=tokens_used,
                    revisions_used=revisions_used,
                    artifact_version=record.version,
                    spec_digest=record.spec_digest,
                )
            if attempt < spec.max_revisions:
                revisions_used += 1

        error_msg = (
            f"Max revision budget exhausted after {revisions_used} revisions "
            f"(max_revisions={spec.max_revisions})."
        )
        record = self.registry.register(
            spec=spec,
            status="failed_revisions",
            output=last_output,
            tokens_used=tokens_used,
            revisions_used=revisions_used,
        )
        return ChildEvalResult(
            spec_id=spec.spec_id,
            status="failed_revisions",
            output=last_output,
            tokens_used=tokens_used,
            revisions_used=revisions_used,
            artifact_version=record.version,
            spec_digest=record.spec_digest,
            error=error_msg,
        )
