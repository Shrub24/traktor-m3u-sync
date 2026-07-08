## Why

This repository is currently only a workflow scaffold, with no reproducible developer environment, no Python project wiring, and no canonical project documentation beyond a code-style note. The project needs a Nix-first bootstrap change now so future NML↔M3U sync work can proceed on top of an agreed toolchain, package layout, and documented repository conventions.

## What Changes

- Add a reproducible Nix-first developer workspace centered on Python 3.14, uv, direnv, treefmt-nix, and a small set of Python quality tools.
- Establish the initial Python package, CLI entry point wiring, test layout, and local task runner structure for the sync worker.
- Add repository-level documentation that records architecture direction, near-term plan, agent guidance, and conventions for keeping repo docs aligned with implementation decisions.
- Introduce lightweight local automation such as formatting, checks, and pre-commit-style hooks without overbuilding CI in this phase.

## Capabilities

### New Capabilities
- `developer-workspace`: Provide a reproducible developer environment, Python project wiring, local automation commands, and baseline quality tooling for the repository.
- `repository-governance`: Provide canonical repository documentation and guidance that define architecture direction, conventions, and ongoing documentation maintenance expectations.

### Modified Capabilities

- None.

## Impact

- Adds `flake.nix`, direnv support, Python packaging metadata, formatting/check/type/test tool configuration, and local hook wiring.
- Adds top-level repository documents such as `AGENTS.md`, `ARCHITECTURE.md`, `PLAN.md`, and likely `CONVENTIONS.md` plus any required README updates.
- Establishes the initial `src/traktor_m3u_sync/` and `tests/` structure used by later functional changes.
- Sets the baseline developer workflow that later export/import changes must follow.
