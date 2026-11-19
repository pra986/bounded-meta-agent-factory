# Bounded Meta-Agent Factory

**Project 23 / A7: Agentic Track — Agent Creator (Legacy AutoGen Pattern)**

A declarative meta-agent factory enforcing strict runtime safety boundaries: recursion depth `<= 1`, read-only tool allowlists, token budget caps, isolated child instantiation without raw `exec`/`eval`, bounded revisions (`max_revisions=2`), and a versioned artifact registry.

---

## Architecture

Instead of allowing a parent agent to dynamically generate and `exec()` arbitrary Python code for child agents, `BoundedMetaAgentFactory` separates **declarative specification** from **isolated execution**:

```
Parent Agent (depth=0)
  │
  ▼  AgentSpec (declarative JSON/Pydantic contract)
[1. Spec Validation] ──► PolicyValidationResult (allowlist, depth <= 1, budget)
  │
  ▼  (approved)
[2. Isolated Child Runner] ──► Template Registry (no raw exec / eval)
  │
  ▼  ChildEvalResult (typed output, tokens_used, revision_count)
[3. Bounded Revision Loop] ◄── max_revisions = 2
  │
  ▼
[4. Versioned Artifact Registry] ──► Immutable SHA-256 versioned snapshots
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full component and invariant details.

---

## 6-Stage Workflow

1. **Declarative Spec Authoring**: The parent agent emits a typed `AgentSpec` declaring `name`, `role`, `goal`, `allowed_tools`, `token_budget`, `recursion_depth`, `max_revisions`, and `template_id`.
2. **Policy & Allowlist Validation**: `BoundedMetaAgentFactory.validate_spec()` checks that `recursion_depth <= 1`, `spawn_children` is disabled at depth 1, all requested tools belong to `APPROVED_READ_ONLY_TOOLS`, `token_budget` is within `[1, max_token_budget]`, and `max_revisions <= 2`.
3. **Isolated Child Instantiation**: Approved specs are bound to a pre-registered declarative template handler inside an isolated runner—never via `exec()`, `eval()`, or dynamic module imports.
4. **Bounded Execution & Token Metering**: Each child invocation tracks token consumption against `spec.token_budget` and halts immediately on budget exhaustion.
5. **Bounded Revision Loop (`max_revisions=2`)**: If child evaluation fails quality checks, the factory allows at most `max_revisions=2` refinement attempts before halting with a terminal failure.
6. **Versioned Artifact Registration & Typed Delivery**: Every completed or halted run records an immutable versioned snapshot in `ArtifactRegistry` and returns a typed `ChildEvalResult` to the parent agent.

---

## Data Contract

Defined in `meta_factory/models.py`:

- **`AgentSpec`**: `spec_id`, `name`, `role`, `goal`, `template_id`, `allowed_tools`, `token_budget`, `recursion_depth` (`<= 1`), `spawn_children` (`bool`), `max_revisions` (`<= 2`).
- **`PolicyValidationResult`**: `approved` (`bool`), `violations` (`list[str]`), `sanitized_tools` (`list[str]`), `effective_depth` (`int`).
- **`ChildEvalResult`**: `spec_id`, `status` (`"completed" | "rejected" | "failed_budget" | "failed_revisions"`), `output` (`dict[str, Any] | None`), `tokens_used` (`int`), `revisions_used` (`int`), `artifact_version` (`int | None`), `error` (`str | None`).

---

## Production Controls

| Control | Enforcement |
| :--- | :--- |
| **Recursion Depth** | Hard cap `recursion_depth <= 1`; child agents cannot spawn grandchildren. |
| **Tool Allowlist** | Read-only allowlist (`read_file`, `search_docs`, `query_metrics`, `list_artifacts`, `inspect_schema`). |
| **No Raw `exec`** | Declarative template registry only; `exec`/`eval` are prohibited. |
| **Token Budget** | Per-spec cap validated pre-flight and metered per revision. |
| **Bounded Revisions** | `max_revisions` capped at `2`; prevents infinite critique/revise loops. |
| **Artifact Registry** | Monotonic version numbers with SHA-256 spec digests for auditability. |

---

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run CLI demo
python -m meta_factory.cli

# Run test suite
pytest -v
```

---

## Attribution

Adapted from the legacy AutoGen Agent Creator pattern in `ed-donner/agents`:
- `ed-donner/agents` — `README.md`
- `ed-donner/agents` — `5_agent_frameworks/5_agent_loop/lab.md`

## License

MIT License — see [LICENSE](LICENSE).
, token budgets, bounded revisions, and versioned artifact registries.
