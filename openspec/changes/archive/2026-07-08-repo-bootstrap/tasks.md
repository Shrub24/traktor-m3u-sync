## 1. Establish repository structure and docs

- [x] 1.1 Add root documentation including `AGENTS.md`, `ARCHITECTURE.md`, `PLAN.md`, and any needed supporting convention or README files.
- [x] 1.2 Align `CODE_STYLE.md` and the new repo docs so they consistently describe fail-fast behavior, documentation maintenance expectations, and the agreed toolchain.
- [x] 1.3 Create the initial `src/traktor_m3u_sync/` and `tests/` structure with a minimal CLI wiring placeholder suitable for later sync features.

## 2. Bootstrap project metadata and workspace

- [x] 2.1 Add the Nix-first workspace files, including `flake.nix`, direnv support, and treefmt-nix configuration for the preferred Python 3.14 workflow.
- [x] 2.2 Add Python project metadata and dependency wiring with `uv`, `hatchling`, package/CLI naming, and baseline dev tools.
- [x] 2.3 Add `just` recipes and lightweight `lefthook` automation for the canonical local format, lint, type, and test flows.

## 3. Verify and prepare for follow-on changes

- [x] 3.1 Verify that the documented bootstrap workflow exposes the canonical local commands and repository guidance needed by future changes.
- [x] 3.2 Run the required OpenSpec and scoped project validation checks for the bootstrap artifacts and workspace wiring.
