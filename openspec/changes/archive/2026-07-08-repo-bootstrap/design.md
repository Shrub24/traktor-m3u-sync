## Context

`traktor-m3u-sync` is a greenfield repository intended to become a Nix-first Python CLI worker for two-way synchronization between Traktor `collection.nml` playlists and UTF-8 `.m3u8` files. Before implementing export or import behavior, the repository needs a stable development baseline: reproducible tooling, a minimal package structure, and canonical documents that capture the project's conventions and planned architecture.

The user has already set several non-negotiable conventions: prefer Python 3.14, keep packaging and local development Nix-first, use modern Python tooling (`uv`, `pytest`, `pyright`, `typer`), use `treefmt-nix` where practical for formatting, keep automation lightweight, and document all repo conventions in a durable way that future agents must maintain.

## Goals / Non-Goals

**Goals:**
- Create a reproducible local developer workspace that works from Nix, direnv, and uv.
- Establish the minimum Python package and CLI wiring needed for later sync features.
- Standardize formatting, linting, typing, tests, and local hooks with minimal ceremony.
- Create canonical repository documentation that records architecture direction, near-term roadmap, and maintenance expectations for conventions.
- Avoid locking the project into unnecessary infrastructure before functional work starts.

**Non-Goals:**
- Implement NML parsing, M3U export, sandbox import, or any sync logic.
- Build a full CI/CD pipeline, deployment module, or production systemd integration.
- Finalize every future architectural decision beyond what is required to bootstrap the repository safely.

## Decisions

### 1. Use a Nix-first workspace with Python 3.14 as the preferred runtime
- **Decision:** The repository will define a `flake.nix` developer shell that provides Python 3.14 and project tooling, with `.envrc` used to enter the environment automatically.
- **Rationale:** The project is expected to run in a Nix-managed environment and should keep local setup reproducible across machines. Python 3.14 is the preferred target and is believed to be compatible with current dependencies.
- **Alternatives considered:**
  - Pure uv-managed local environments without Nix: rejected because Nix is the primary packaging/runtime lane.
  - Older Python targets such as 3.12/3.13: deferred unless dependency compatibility proves otherwise during implementation.

### 2. Keep Python dependency and packaging management modern but minimal
- **Decision:** Use `uv` for dependency management and lockfiles, `hatchling` for the build backend, and a standard `src/` package layout with CLI entry-point wiring through the package metadata.
- **Rationale:** `uv` is the agreed modern default, works well with a Nix-first project, and keeps dependency workflows simple. `hatchling` keeps packaging lightweight without introducing extra project-management abstractions.
- **Alternatives considered:**
  - Poetry/PDM: rejected as unnecessary additional workflow surface.
  - setuptools: acceptable, but less aligned with the desired modern baseline.

### 3. Use treefmt-nix plus narrow quality tools rather than bespoke formatting scripts
- **Decision:** Use `treefmt-nix` to coordinate formatting, while relying on a compact toolchain such as Ruff, Pyright, and pytest for lint/type/test coverage.
- **Rationale:** This preserves a Nix-native workflow, reduces ad hoc scripting, and keeps formatting behavior centralized.
- **Alternatives considered:**
  - Tool-specific shell scripts only: rejected because formatting policy would be less discoverable and less consistent.
  - Overbuilt CI or many overlapping tools: rejected for phase-0 simplicity.

### 4. Keep local automation lightweight with just recipes and lefthook
- **Decision:** Provide `just` recipes for the common commands and use `lefthook` for fast local hook automation.
- **Rationale:** `CODE_STYLE.md` already requires `just` recipes, and lightweight hooks can enforce the same local checks without introducing a large CI-first workflow.
- **Alternatives considered:**
  - No hook tooling: rejected because the repo should make the happy path easy.
  - Heavy CI orchestration in this change: rejected as premature.

### 5. Treat repository documentation as an explicit capability, not incidental prose
- **Decision:** Add top-level docs that separate concerns: `AGENTS.md` as the index and agent directive, `ARCHITECTURE.md` for high-level technical direction, `PLAN.md` for near-term execution roadmap, and `CONVENTIONS.md` for repo workflow/tooling rules if that improves clarity.
- **Rationale:** The user explicitly wants conventions, architecture, and agent directives documented and kept current. Making documentation part of the bootstrap contract prevents it from becoming optional.
- **Alternatives considered:**
  - Folding everything into `README.md`: rejected because it overloads one document and weakens navigability.
  - Relying only on OpenSpec artifacts: rejected because some guidance must remain visible at the repo root.

## Risks / Trade-offs

- **[Python 3.14 ecosystem drift]** Some dependencies may claim support but still have rough edges on 3.14. → **Mitigation:** verify the chosen toolchain during implementation and only introduce a lower fallback if an actual blocker appears.
- **[Too much tooling too early]** Bootstrap work can become an infrastructure sink. → **Mitigation:** keep CI skeletal, prefer local workflows, and defer anything not required for functional sync work.
- **[Documentation duplication]** Repo-root docs and OpenSpec artifacts can diverge. → **Mitigation:** make `AGENTS.md` and conventions explicitly require updates when project decisions change.
- **[Nix/Python workflow overlap]** uv and Nix can duplicate responsibilities. → **Mitigation:** define Nix as the environment provider and uv as the Python dependency/package workflow inside that environment.

## Migration Plan

This is an initial bootstrap change, so migration is additive:
1. Add the new workspace, package, and documentation files.
2. Verify local commands for format, lint, types, and tests.
3. Use the new documented structure as the baseline for subsequent OpenSpec changes.

Rollback is straightforward: revert the bootstrap commit or change set before feature work depends on it.

## Open Questions

- Whether the final implementation should pin Python 3.14 only or retain a documented fallback range if a real compatibility issue appears.
- Which exact treefmt formatters should be enabled beyond Python and Nix files.
- Whether the bootstrap change should add a placeholder CI workflow file now or leave CI entirely to a later change.
