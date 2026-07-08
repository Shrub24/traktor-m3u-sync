# traktor-m3u-sync

CLI worker for bidirectional synchronization between Traktor Pro playlist collections (`collection.nml`) and standard UTF-8 `.m3u8` playlists.

## Status

**Phase 0 complete** — repo tooling, package wiring, and canonical docs are in place. No sync logic implemented yet.

Next up: [Phase 1 — NML export foundation](PLAN.md).

## Quick start

```bash
# enter the dev environment (Nix + direnv)
direnv allow   # or: nix develop

# install deps and hooks
just setup

# run all checks
just check
```

## Commands

| Command         | What it does                                     |
| --------------- | ------------------------------------------------ |
| `just setup`      | sync Python deps (`uv sync --dev`) and install git hooks |
| `just fmt`        | auto-format all files (`nix fmt`)                  |
| `just fmt-check`  | check formatting without rewriting (`nix flake check`) |
| `just lint`       | run Ruff linter                                    |
| `just type`       | run Pyright type checker                           |
| `just test`       | run pytest                                         |
| `just check`      | all of the above (fmt-check + lint + type + test)  |
| `just lock`       | regenerate `uv.lock`                               |

## Project layout

```
.
├── src/traktor_m3u_sync/   # Python package (CLI entry point)
├── tests/                  # pytest test suite
├── openspec/               # change proposals, specs, archive
├── flake.nix               # Nix workspace (Python 3.14, tools)
├── treefmt.nix             # formatting config (nixfmt, ruff)
├── pyproject.toml          # Python project metadata and tool config
├── justfile                # task runner recipes
├── lefthook.yml            # pre-commit hooks
└── docs...
```

## Architecture

Six-layer design, each implemented as a dedicated module:

1. **Config** — path mappings, sync mode, sandbox settings
2. **NML domain** — load/inspect Traktor `collection.nml` via `traktor-nml-utils`
3. **M3U domain** — read/write UTF-8 `.m3u8` playlists
4. **Path translation** — Traktor `VOLUME`/`DIR`/`FILE` ↔ Unix paths
5. **Sync orchestration** — export (NML→M3U) and import (M3U→NML sandbox) workflows
6. **Reporting** — sync summaries, unmatched track warnings

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details and NML format notes.

## Roadmap

| Phase | Focus                                       | Status      |
| ----- | ------------------------------------------- | ----------- |
| 0     | Repo bootstrap, tooling, docs               | ✓ Done      |
| 1     | NML → M3U8 export                           | Next        |
| 2     | M3U8 → NML sandbox import                   | Planned     |
| 3     | Config/reporting polish, operational niceties | Planned   |
| 4     | Smartlists, watch mode, Navidrome, etc.     | Deferred    |

See [PLAN.md](PLAN.md) for the full plan and tentative OpenSpec change trajectory.

## Canonical docs

| Doc                                             | Purpose                                             |
| ----------------------------------------------- | --------------------------------------------------- |
| [AGENTS.md](AGENTS.md)                           | Agent directives, source-of-truth rules, tool routing |
| [CODE_STYLE.md](CODE_STYLE.md)                   | Python coding style and implementation philosophy   |
| [CONVENTIONS.md](CONVENTIONS.md)                 | Repo conventions, toolchain defaults, workflow rules |
| [ARCHITECTURE.md](ARCHITECTURE.md)               | System direction, NML format reference, decisions   |
| [PLAN.md](PLAN.md)                               | Phased roadmap and OpenSpec change trajectory       |
| `openspec/specs/`                                  | Canonical capability specs                          |
| `openspec/changes/`                                | Active change proposals and task state              |
| `openspec/changes/archive/`                        | Completed changes                                   |

## License

GPL-compatible (exact license TBD).

## Dependencies

- [traktor-nml-utils](https://github.com/wolkenarchitekt/traktor-nml-utils) — NML parsing via xsdata dataclasses
- [typer](https://typer.tiangolo.com/) — CLI framework
- Python 3.14+, managed via [uv](https://github.com/astral-sh/uv)
