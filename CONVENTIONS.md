# Repository Conventions

## Design principles

- Prefer clear, concise, modern, idiomatic Python.
- Keep logic explicit and composable.
- Validate at I/O boundaries; trust internal invariants afterward.
- Fail fast on unexpected states and let stack traces stay visible unless a runtime condition is explicitly handled.
- Prefer configuration and composition over hidden globals and ad hoc environment reads.
- Avoid speculative architecture and premature generalization.

## Toolchain defaults

- Nix is the primary environment and packaging lane.
- Python 3.14 is the preferred runtime target.
- `uv` manages Python dependencies and lockfiles.
- `hatchling` is the default build backend.
- `typer` is the default CLI framework.
- `pytest` is the default test runner.
- `pyright` is the default type checker.
- Ruff is the default Python lint tool.
- `treefmt-nix` coordinates formatting.
- `just` exposes canonical project commands.
- `lefthook` provides lightweight local hook automation.
- TOML is the config file format.
- Package name: `traktor_m3u_sync`
- CLI name: `traktor-m3u-sync`
- License: GPL-3.0-or-later

## Repo workflow

- Start from OpenSpec for any non-trivial scoped change.
- Execute tasks from `openspec/changes/<change>/tasks.md` and keep checkboxes current.
- Keep docs and implementation aligned within the same change.
- Prefer minimal, incremental diffs that preserve future flexibility.

## Documentation rules

- Root docs describe durable repo guidance.
- OpenSpec artifacts describe change-specific intent and execution.
- Update documentation when conventions, architecture, or workflow expectations change.
- If a decision is temporary or provisional, say so explicitly.

## Deployment surfaces

- The flake exposes a runtime package (`packages.<system>.traktor-m3u-sync`) built with `buildPythonApplication`.
- A flake app (`apps.<system>.default`) wraps the package for `nix run` convenience.
- A NixOS module (`nixosModules.traktor-m3u-sync`) provides named state domains and independently triggerable import/export jobs through shared systemd templates.
- The module renders one TOML config per generated job from its referenced state and selected format; a job-level `configFile` may provide externally managed TOML instead.
- Orchestration policy (timers, path units, consumer hooks, and Engine availability coordination) is intentionally excluded from the base module — downstream consumers attach it through standard NixOS mechanisms.
- The TOML config contract remains the primary CLI interface; the module's Nix-level options map 1:1 to the same TOML structure.

## Formatting and checks

- Use repo-provided commands rather than one-off shell snippets when available.
- Keep formatting automated and deterministic.
- Prefer the canonical `just` entry points (`setup`, `fmt`, `fmt-check`, `lint`, `type`, `test`, `check`, `lock`, `pkg-build`, `app-run`, `module-check`) over direct tool invocation during normal development.
- Run the smallest meaningful validation set for the current change, then run required OpenSpec validation before handoff.

## Scope control

- Bootstrap changes should not overbuild CI/CD or deployment.
- Functional sync features should arrive in later dedicated changes.
- Navidrome-specific automation is explicitly out of scope for the current repo bootstrap phase.
