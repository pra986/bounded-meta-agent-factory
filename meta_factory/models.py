from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """Declarative specification for a bounded child agent."""

    spec_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    template_id: str = Field(default="read_only_analyst")
    allowed_tools: list[str] = Field(default_factory=list)
    token_budget: int = Field(default=2000, ge=1)
    recursion_depth: int = Field(default=1, ge=0)
    spawn_children: bool = Field(default=False)
    max_revisions: int = Field(default=2, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyValidationResult(BaseModel):
    """Result of validating an AgentSpec against factory safety invariants."""

    approved: bool
    violations: list[str] = Field(default_factory=list)
    sanitized_tools: list[str] = Field(default_factory=list)
    effective_depth: int = 1


class ChildEvalResult(BaseModel):
    """Typed result or terminal failure delivered back to the parent agent."""

    spec_id: str
    status: Literal[
        "completed",
        "rejected",
        "failed_budget",
        "failed_revisions",
        "failed_runtime",
    ]
    output: dict[str, Any] | None = None
    tokens_used: int = 0
    revisions_used: int = 0
    artifact_version: int | None = None
    spec_digest: str | None = None
    error: str | None = None
