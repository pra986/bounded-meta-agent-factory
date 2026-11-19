# Bounded Meta-Agent Factory Architecture

## Overview

`bounded-meta-agent-factory` implements a declarative meta-agent creation pattern (Project 23 / A7: Agentic Track — Legacy AutoGen Pattern) with strict runtime safety boundaries. Instead of executing dynamically generated code via `exec` or `eval`, the parent factory validates a typed `AgentSpec` against static policy rules and instantiates pre-registered, read-only child templates.

## Core Components

1. **Declarative Models (`meta_factory/models.py`)**
   - `AgentSpec`: Defines `spec_id`, `name`, `role`, `goal`, `template_id`, `allowed_tools`, `token_budget`, `recursion_depth`, `spawn_children`, and `max_revisions`.
   - `PolicyValidationResult`: Captures `approved`, `violations`, `sanitized_tools`, and `effective_depth`.
   - `ChildEvalResult`: Returns a typed terminal outcome (`completed`, `rejected`, `failed_budget`, `failed_revisions`, or `failed_runtime`) along with `tokens_used`, `revisions_used`, `artifact_version`, `spec_digest`, and `error`.

2. **Policy & Execution Engine (`meta_factory/engine.py`)**
   - **Read-Only Tool Allowlist**: Only `APPROVED_READ_ONLY_TOOLS` (`read_file`, `search_docs`, `query_metrics`, `list_artifacts`, `inspect_schema`) are permitted.
   - **Depth-1 Recursion Cap**: `MAX_RECURSION_DEPTH = 1` and `spawn_children = False` prevent unbounded nested agent spawning.
   - **Token & Revision Bounds**: Execution halts immediately if `tokens_used > token_budget` or `revisions_used` reaches `max_revisions`.
   - **Versioned Artifact Registry**: `ArtifactRegistry` records immutable `ArtifactRecord` entries keyed by `spec_id` with SHA-256 `spec_digest` and monotonic `version` numbers.

3. **CLI Demo (`meta_factory/cli.py`)**
   - Provides `meta-factory-demo` to demonstrate valid execution, disallowed tool rejection, and depth-2 recursive spawn blocking.

## Execution Flow

```
Parent Request -> AgentSpec -> validate_spec()
                                 |-- violations --> ChildEvalResult(status="rejected")
                                 |-- approved ----> run_child() loop (<= max_revisions)
                                                      |-- budget exceeded --> failed_budget
                                                      |-- retries exhausted -> failed_revisions
                                                      |-- success ----------> ArtifactRegistry + completed
```
