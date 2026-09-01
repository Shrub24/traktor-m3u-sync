# traktor-m3u-sync

CLI worker for synchronizing Traktor Pro playlist collections (`collection.nml`) and standard
UTF-8 `.m3u8` playlists through a local store, with additional export to iTunes XML and an
Engine DJ media database for DJ software.

## Status

**Store-mediated bridge** — every format talks to one internal playlist model through adapters:

```
collection.nml ──import──▶ SQLite store ──export──▶ .m3u8 / iTunes XML / Engine m.db
       .m3u8   ──import──▶            ◀──export──  collection.nml
```

`import` reads a whole source into the store (wholesale rebuild). `export` writes the store to a
whole target and never reads another format. The store is a rebuildable cache: delete it and
re-import at any time.

Current limitations:

- smartlists are skipped with warnings during NML import
- Engine export is M-only: it writes one media-drive `m.db` and mirrors no L: main-library database
- Engine export only references tracks Engine already discovered; it never inserts tracks or changes analysis
- sanitized-name mismatch is a documented limitation (original names are not restored on import)
- reporting is structured stdout/stderr only for now
- no incremental sync; every import replaces the whole snapshot

## Quick start

```bash
# enter the dev environment (Nix + direnv)
direnv allow   # or: nix develop

# install deps and hooks
just setup

# run all checks
just check
```

## Configuration

Create a TOML config file such as `traktor-m3u-sync.toml`. Sections are per format, not per
command direction, and each format owns its library root. Commands validate only the fields of
the formats they select — M3U-to-iTunes needs no NML configuration:

```toml
[store]
path = "~/.local/state/traktor-m3u-sync/store.db"   # optional, this is the default

[nml]
collection_path = "/path/to/collection.nml"
library_root = "C:/Music"                           # Traktor library root (Windows path format); NML commands only
sandbox_name = "Imported Playlists"                 # optional, this is the default

[m3u]
library_root = "../music"                           # M3U library root (absolute or relative); M3U commands only
output_dir = "/path/to/playlists"                   # required for `export --format m3u`
import_dir = "/path/to/incoming"                    # required for `import --format m3u`

[itunes]
output_file = "/path/to/iTunes Music Library.xml"   # required for `export --format itunes`
location_base = "file://localhost/M:/Music"         # consumer-facing library root as a full `file:` URI, ditto
check_base_path = "/path/to/music"                  # optional worker mount, used only for file-missing warnings

[engine]
database_path = "/path/to/Engine Library/Database2/m.db"  # existing Engine DJ 5.0 media database; required for `export --format engine`
track_path_prefix = ".."                            # optional, this is the default; prepended to store-relative paths when matching tracks
managed_root = "Playlist Sync"                      # optional, this is the default; the only playlist subtree export owns
```

> **Breaking migration (format-path-mappings):** the global `[library]` table is gone — move
> `traktor_root` to `[nml].library_root` and `m3u_root` to `[m3u].library_root`. `[itunes].base_path`
> is replaced by `location_base`, a complete `file:` URI of the library root *as the DJ consumer sees
> it* (`file://localhost/M:/Music`, `file:///srv/music`, or UNC `file://server/share/music`); track
> Locations are rendered from it regardless of the worker's own filesystem. Add `check_base_path`
> only if the worker has a local mount worth warning on.

## Commands

```bash
# source -> store
traktor-m3u-sync import --format nml --config traktor-m3u-sync.toml
traktor-m3u-sync import --format m3u --config traktor-m3u-sync.toml

# store -> target (fails fast if the store is empty: run an import first)
traktor-m3u-sync export --format m3u --config traktor-m3u-sync.toml
traktor-m3u-sync export --format nml --config traktor-m3u-sync.toml
traktor-m3u-sync export --format itunes --config traktor-m3u-sync.toml
traktor-m3u-sync export --format engine --config traktor-m3u-sync.toml
```

Per-command overrides:

```bash
traktor-m3u-sync import --format m3u \
  --config traktor-m3u-sync.toml \
  --store /tmp/store.db \
  --collection /path/to/collection.nml \
  --import-dir /path/to/incoming

traktor-m3u-sync export --format nml \
  --config traktor-m3u-sync.toml \
  --collection /path/to/collection.nml \
  --sandbox-name "My Sandbox"

traktor-m3u-sync export --format itunes \
  --config traktor-m3u-sync.toml \
  --output-file "/path/to/iTunes Music Library.xml" \
  --location-base "file://localhost/M:/Music" \
  --check-base-path /path/to/music

traktor-m3u-sync export --format engine \
  --config traktor-m3u-sync.toml \
  --engine-database "/mnt/engine/Engine Library/Database2/m.db" \
  --engine-track-prefix ".." \
  --engine-managed-root "Playlist Sync"
```

A store written by an older schema version is rejected with a structured error pointing at
re-import; there are no migrations.

## Operational flags

- `export --dry-run` (all formats): validates config and store state, then runs the real
  exporter against isolated temporary targets — a temporary directory (M3U), a temporary XML
  file (iTunes), a temporary copy of the collection (NML), or a temporary copy of the database
  (Engine). Output, warnings, and the summary are identical to a real run; the configured
  target, any backup beside it, and the store are left unchanged.
- `--fail-on-warning` (import and export, opt-in): the command still prints its normal
  summary and warnings, then exits `2` when at least one warning was emitted.

Exit statuses: `0` success (including warnings by default), `1` any error, `2` completed
with warnings under `--fail-on-warning`.

M3U and iTunes generated targets are published atomically: each write goes to a same-directory
temporary file and only replaces the target after serialization succeeds. A failed write leaves
a prior target byte-for-byte unchanged and removes its temporary file. Engine publication is
stricter because its target is not disposable; see below.

## Deployment (Nix)

The flake exposes a runtime package, an app shortcut, and a NixOS module.
See [docs/nix-deployment.md](docs/nix-deployment.md) for the full Nix reference
(flake outputs, module options, the Engine export run order, configFile behavior,
systemd timer examples, and `traktor-nml-utils` packaging notes).

### Build the package

```bash
nix build .#packages.x86_64-linux.traktor-m3u-sync
./result/bin/traktor-m3u-sync --help
```

### Run via `nix run`

```bash
nix run .#default -- import --format nml --config traktor-m3u-sync.toml
nix run .#default -- export --format m3u --config traktor-m3u-sync.toml
```

### NixOS module

The flake exposes `nixosModules.traktor-m3u-sync` with declarative service
configuration. The module renders a TOML config into the Nix store and runs
separate oneshot `import` and `export` systemd services. See
[docs/nix-deployment.md](docs/nix-deployment.md) for the option reference.

#### Config override

Set `configFile` to use an externally managed TOML file instead of rendering
from Nix options:

```nix
services.traktor-m3u-sync = {
  enable = true;
  configFile = "/etc/traktor-m3u-sync/config.toml";
  export = {
    enable = true;
    format = "m3u";
  };
  import = {
    enable = true;
    format = "nml";
  };
};
```

When `configFile` is set, the module uses it directly and skips its
generated-config assertions. The per-service `format` is still required —
it is passed to the CLI as `--format`.

#### Downstream orchestration

Services are oneshot units with `wantedBy = []` by default — no timers, path
triggers, or Syncthing hooks are bundled. Attach scheduling or filesystem
triggers in your own NixOS config (e.g. `systemd.timers` or Syncthing folder
watch hooks) as downstream orchestration policy. The module adds no flags of
its own; operators that want warning-sensitive oneshots override the service
`ExecStart` downstream and append `--fail-on-warning` (see
[docs/nix-deployment.md](docs/nix-deployment.md)).

## Commands

| Command           | What it does                                               |
| ----------------- | ---------------------------------------------------------- |
| `just setup`      | sync Python deps (`uv sync --dev`) and install git hooks   |
| `just fmt`        | auto-format all files (`nix fmt`)                          |
| `just fmt-check`  | check formatting without rewriting (`nix flake check`)     |
| `just lint`       | run Ruff linter                                            |
| `just type`       | run Pyright type checker                                   |
| `just test`       | run pytest                                                 |
| `just run-export` | run the export CLI with the local config                   |
| `just check`      | all of the above (fmt-check + lint + type + test)          |
| `just lock`       | regenerate `uv.lock`                                       |
| `just pkg-build`  | build the Nix runtime package                              |
| `just app-run`    | run the CLI via `nix run`                                  |
| `just module-check` | evaluate the NixOS module with a minimal config          |

## NML import behavior (`import --format nml`)

- reads every standard playlist from `collection.nml`, preserving folder hierarchy and `$ROOT` omission
- prefers `PRIMARYKEY` for track paths and falls back to reconstructed `LOCATION`
- stores track duration in seconds (Traktor's `PLAYTIME` milliseconds are converted at the adapter)
- emits structured warnings for skipped smartlists and unmappable paths

## M3U export behavior (`export --format m3u`)

- writes one UTF-8 `.m3u8` file per playlist, mirroring the stored folder hierarchy
- renders paths from `[m3u].library_root` only, without consulting NML configuration
- minimally sanitizes filesystem-invalid playlist and folder names
- skips stored tracks with no resolvable path, with structured warnings

## M3U import behavior (`import --format m3u`)

- reads a directory tree of `.m3u8` files: nested directories become playlist folders
- a flat directory becomes playlists directly under the sandbox root
- no hierarchy is inferred from filenames

## NML export behavior (`export --format nml`)

- rebuilds a single managed sandbox folder inside `collection.nml` from stored state
- matches stored tracks against existing collection entries by normalizing them through `[nml].library_root`
- writes playlist entries as `PRIMARYKEY` references only (no metadata duplication)
- creates a timestamped backup of `collection.nml` before every save
- validates the saved file reloads and the sandbox structure is correct, restoring the backup on failure
- skips unmatched tracks with structured warnings rather than failing
- idempotent: running the same export twice produces the same result

## Engine export behavior (`export --format engine`)

Engine DJ 5.0 keeps playlists in SQLite, so this export mutates a database instead of writing a file.

- requires Engine DJ closed; stopping the Windows VM is sufficient but not required. A non-empty
  `-journal` sidecar or any `-wal`/`-shm` file fails the run before anything is written
- targets only the media-drive database named by `[engine].database_path`; the L: main-library
  database is never mirrored
- matches store paths as `<track_path_prefix>/<store-relative-path>` against `Track` rows that
  already exist in that database; missing, unresolved, ambiguous, and duplicate references warn
  and skip instead of creating tracks
- never creates a database or mutates Engine analysis, cues, waveforms, artwork, or tags
- owns exactly one top-level subtree (`[engine].managed_root`), rebuilt idempotently while
  unrelated Engine playlists stay untouched
- requires schema 3.0.2 in rollback-journal (`DELETE`) mode; anything else fails before staging
- publishes a mode-preserving same-directory stage: the current target is refreshed into the
  adjacent `<database-name>.playlist-sync.bak` (one generation, retained on success), the stage
  replaces the target atomically, and a post-publication validation failure restores that backup.
  The published inode is owned by the worker identity and gets its group from the target directory

Run order: close Engine DJ (or stop the VM) → `export --format engine --dry-run` → real export →
check matched tracks, playlists, memberships, and skips in the summary → open Engine DJ. Rollback is
the operator's own step against the retained backup, taken while Engine stays offline.

## Track identity

- primary identity is the casefolded POSIX library-relative path
- tracks with no resolvable path fall back to a casefolded, whitespace-collapsed `artist - title` key
- ambiguous fallback collisions are stored flagged as unresolved with their raw path, and are
  excluded from identity dedup and from targets that need a path

## Project layout

```
.
├── src/traktor_m3u_sync/   # Python package (CLI entry point)
├── tests/                  # pytest test suite
├── nix/
│   ├── packages/           # Nix package definitions (traktor-nml-utils)
│   └── modules/            # NixOS module definitions
├── openspec/               # change proposals, specs, archive
├── flake.nix               # Nix workspace (packages, apps, modules)
├── treefmt.nix             # formatting config (nixfmt, ruff)
├── pyproject.toml          # Python project metadata and tool config
├── justfile                # task runner recipes
├── lefthook.yml            # pre-commit hooks
└── docs...
```

## Architecture

Store-mediated layers, each a dedicated module under `src/traktor_m3u_sync/`:

1. **Config** — format-based TOML sections and per-command overrides
2. **Model** — frozen playlist/track dataclasses plus identity normalization
3. **Store** — SQLite snapshot of imported playlists (schema-versioned, rebuildable)
4. **Contracts** — importer/exporter protocols, path-mapping protocol, shared warning/result types
5. **Paths** — adapter-owned roots translating native path spaces to/from library-relative paths, plus a consumer `file:` URI mapping for iTunes
6. **Formats** — `nml` and `m3u` adapters (importer + exporter per format) plus the export-only
   `itunes` and `engine` adapters; `engine` writes into an existing database rather than a file
7. **Services** — `run_import` / `run_export` orchestration and the CLI surface

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details and NML format notes.

## Roadmap

| Phase | Focus                                       | Status      |
| ----- | ------------------------------------------- | ----------- |
| 0     | Repo bootstrap, tooling, docs               | ✓ Done      |
| 1     | NML → M3U8 export                           | ✓ Done      |
| 2     | M3U8 → NML sandbox import                   | ✓ Done      |
| 3     | Config/reporting polish, deployment surfaces | In Progress |
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

This project is licensed under **GPL-3.0-or-later**.

## Dependencies

- [traktor-nml-utils](https://github.com/wolkenarchitekt/traktor-nml-utils) — NML parsing via xsdata dataclasses
- [typer](https://typer.tiangolo.com/) — CLI framework
- Python 3.14+, managed via [uv](https://github.com/astral-sh/uv)
