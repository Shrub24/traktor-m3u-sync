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
- License direction: GPL-compatible

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

## Formatting and checks

- Use repo-provided commands rather than one-off shell snippets when available.
- Keep formatting automated and deterministic.
- Prefer the canonical `just` entry points (`setup`, `fmt`, `fmt-check`, `lint`, `type`, `test`, `check`, `lock`) over direct tool invocation during normal development.
- Run the smallest meaningful validation set for the current change, then run required OpenSpec validation before handoff.

## Scope control

- Bootstrap changes should not overbuild CI/CD or deployment.
- Functional sync features should arrive in later dedicated changes.
- Navidrome-specific automation is explicitly out of scope for the current repo bootstrap phase.
