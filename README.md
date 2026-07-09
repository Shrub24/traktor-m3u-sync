# traktor-m3u-sync

CLI worker for bidirectional synchronization between Traktor Pro playlist collections (`collection.nml`) and standard UTF-8 `.m3u8` playlists.

## Status

**Phase 1 export and Phase 2 sandbox import available** — the repository can now export standard playlists from Traktor `collection.nml` into UTF-8 `.m3u8` files, and import `.m3u8` playlists back into a managed sandbox folder in `collection.nml`.

Current limitations:

- smartlists are skipped with warnings
- sanitized-name mismatch is a documented limitation (original names are not restored on import)
- reporting is structured stdout/stderr only for now

## Quick start

```bash
# enter the dev environment (Nix + direnv)
direnv allow   # or: nix develop

# install deps and hooks
just setup

# run all checks
just check
```

## Export configuration

Create a TOML config file such as `traktor-m3u-sync.toml`:

```toml
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/path/to/collection.nml"
output_dir = "/path/to/playlists"
```

Then run:

```bash
traktor-m3u-sync export --config traktor-m3u-sync.toml
```

You can override export workflow paths on the CLI:

```bash
traktor-m3u-sync export \
  --config traktor-m3u-sync.toml \
  --collection /path/to/collection.nml \
  --output-dir /path/to/playlists
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

## Export behavior

- exports one UTF-8 `.m3u8` file per standard Traktor playlist
- preserves playlist folder hierarchy while omitting `$ROOT`
- prefers `PRIMARYKEY` for track paths and falls back to reconstructed `LOCATION`
- minimally sanitizes filesystem-invalid playlist and folder names
- emits structured warnings for skipped smartlists and unmappable tracks

## Import configuration

To enable import, add an `[import]` section to your config:

```toml
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/path/to/collection.nml"
output_dir = "/path/to/playlists"

[import]
collection_path = "/path/to/collection.nml"
import_dir = "/path/to/m3u-playlists"
sandbox_name = "Imported Playlists"   # optional, defaults to "Imported Playlists"
```

Then run:

```bash
traktor-m3u-sync import --config traktor-m3u-sync.toml
```

You can override import settings on the CLI:

```bash
traktor-m3u-sync import \
  --config traktor-m3u-sync.toml \
  --collection /path/to/collection.nml \
  --import-dir /path/to/m3u-playlists \
  --sandbox-name "My Sandbox"
```

## Import behavior

- rebuilds a single managed sandbox folder inside `collection.nml` from current M3U state
- supports both nested directory layouts (preserving folder hierarchy) and flat directories
- matches imported tracks against existing collection entries via reverse path translation
- writes playlist entries as `PRIMARYKEY` references only (no metadata duplication)
- creates a timestamped backup of `collection.nml` before every save
- validates the saved file can be reloaded and sandbox structure is correct
- skips unmatched tracks with structured warnings rather than failing
- idempotent: running the same import twice produces the same result

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
| 1     | NML → M3U8 export                           | ✓ Done      |
| 2     | M3U8 → NML sandbox import                   | ✓ Done      |
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
