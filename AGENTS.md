# AGENTS

This file is the entry point for agents and contributors working in this repository. Use it as the high-level directive and index for canonical project guidance.

## Canonical documents

- `AGENTS.md`: agent workflow, repo navigation, and documentation maintenance rules
- `CODE_STYLE.md`: coding style and implementation philosophy
- `CONVENTIONS.md`: repo conventions, tooling expectations, and workflow defaults
- `ARCHITECTURE.md`: high-level system direction and technical boundaries
- `PLAN.md`: current phased roadmap and near-term delivery focus
- `openspec/changes/*`: canonical change-specific proposal, design, spec, and task state

## Source of truth rules

1. OpenSpec artifacts are the canonical state for scoped change work.
2. Root docs are the canonical repo-wide guidance for conventions, architecture, and workflow.
3. Do not treat chat history or ad hoc scratch files as source of truth when a canonical document exists.

## Required workflow

1. Read this file first.
2. Read the active OpenSpec change artifacts before implementation.
3. Read `CODE_STYLE.md`, `CONVENTIONS.md`, `ARCHITECTURE.md`, and `PLAN.md` when the task touches repo-wide behavior or structure.
4. Update the relevant docs when implementation decisions materially change conventions, workflow, or architecture.
5. Keep changes DRY, YAGNI, and explicit.

## Documentation maintenance mandate

When implementation discovers or formalizes a durable repo rule, tool choice, workflow expectation, architectural boundary, or agent directive, update the relevant canonical document in the same change.

At minimum, consider whether the change requires updates to:

- `AGENTS.md`
- `CODE_STYLE.md`
- `CONVENTIONS.md`
- `ARCHITECTURE.md`
- `PLAN.md`
- relevant OpenSpec artifacts

Do not defer these updates if the change would leave repo guidance stale.

## Tool routing expectations

Prefer the most idiomatic available tool for the job:

- `codebase-memory-mcp_*`: primary lane for local code graph, symbols, callers, and architectural discovery
- `semble_*`: semantic code or docs discovery before broad file sweeps
- `qmd_*`: local markdown/wiki/note retrieval before external research
- OpenSpec CLI: planning state, apply flow, and validation
- Nix-native tools: environment and formatting orchestration where practical

Use subagents when the workflow is genuinely multi-step or specialized. Favor the dedicated specialist lane over generic delegation.

## Current repo direction

- Nix-first development and packaging workflow
- Python 3.14 preferred
- Modern Python tooling centered on `uv`, `hatchling`, `typer`, `pytest`, `pyright`, and Ruff
- `treefmt-nix` for formatting orchestration
- Lightweight automation with `just` and `lefthook`
- Fail-fast internals, validation at I/O boundaries

## Prohibited habits

- Do not add speculative abstractions.
- Do not over-comment obvious code.
- Do not suppress lint/type issues without explicit agreement.
- Do not hide unexpected internal exceptions behind broad validation or logging layers.
