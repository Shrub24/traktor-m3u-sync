# Architecture

## Purpose

`traktor-m3u-sync` is a Nix-first Python CLI worker that bridges playlist libraries through a multi-format pipeline. Traktor `collection.nml` and UTF-8 `.m3u8` are import/export modalities; iTunes XML, rekordbox XML and Engine DJ are export modalities, with Engine import still deferred.

## Architecture: store-mediated multi-format bridge

The system is a hub-and-spoke bridge. The hub is a format-neutral playlist model plus a local SQLite store; each format is a pair of adapter modules that only translates between its native representation and the hub. Import and export are independent processes that communicate through the store.

1. **Model (`model/`)** — frozen playlist/track dataclasses with identity normalization: a track's identity is its casefolded POSIX library-relative path, with an artist+title fallback only for entries that have no resolvable path (ambiguous fallbacks warn; unresolvable entries are stored flagged, never dropped).
2. **Store (`store/`)** — SQLite (stdlib `sqlite3`) cache at `[store].path`. Rebuildable, disposable state: every import performs a wholesale wipe-and-rebuild in one transaction. A `meta` table carries the schema version; mismatches fail fast with a re-import directive — there are no migrations.
3. **Format adapters (`formats/<fmt>/`)** — per format, an `Importer` (`read(source) -> ImportResult`) and/or `Exporter` (`write(playlists, target) -> ExportResult`) plus format-internal helpers. Adapters emit shared structured warning/result types and hold no cross-format knowledge.
4. **Paths (`paths/`)** — each path-bearing format owns its mapping: `[nml].library_root` and `[m3u].library_root` translate native forms (Traktor `VOLUME`/`DIR`/`FILE`/`PRIMARYKEY`, M3U relative/absolute) to and from library-relative identity space, and a pure `file:` URI mapping renders consumer-facing iTunes Locations from `[itunes].location_base` independent of the worker filesystem.
5. **Services (`services/`)** — thin orchestration only: resolve config, select the format's adapter, run it, rebuild or read the store, summarize. Format selection is a registry lookup.
6. **CLI (`cli.py`)** — `import --format nml|m3u` (source → store) and `export --format nml|m3u|itunes|rekordbox|engine` (store → target). Export reads only the store and fails fast when it is empty or uninitialized.

Adding a format means one adapter package and any required path mapping or config section; no other format needs format-specific orchestration. Engine DJ is the first non-file target format: instead of generating a file it rebuilds playlists inside an existing Engine database.

## Confirmed architectural decisions

- Python 3.14 is preferred.
- Development and packaging are Nix-first.
- CLI-first design; no GUI is planned.
- Command surface is store-mediated: `import --format <fmt>` rebuilds the store from a source; `export --format <fmt>` renders the store to a target and never reads sources directly.
- The store is a rebuildable cache (schema versioned, wholesale rebuild per import, no migrations); external libraries remain the source of truth.
- Track identity is the casefolded POSIX library-relative path; artist+title is a fallback-only identity with ambiguity warnings.
- Traktor playlist import into NML keeps the sandbox overwrite model rather than fine-grained merge logic.
- Missing import matches are skipped and reported.
- Exported playlists use UTF-8 `.m3u8`.
- Durations are stored in seconds; adapters convert native units (Traktor `PLAYTIME` is milliseconds) at the boundary.
- TOML is the configuration format, with format-based sections (`[store]`, `[nml]`, `[m3u]`, `[itunes]`, `[rekordbox]`, `[engine]`) and per-command CLI overrides. There is no global `[library]` table (retired by `format-path-mappings`).
- Library roots belong to their format: `[nml].library_root` and `[m3u].library_root`, each required only when a command selects that format; unselected adapters impose no configuration.
- iTunes Locations and Music Folder render from `[itunes].location_base`, a complete consumer-facing absolute `file:` URI (empty, `localhost`, and UNC authorities supported; UTF-8 percent-encoding preserving `/` and drive colons). Optional `[itunes].check_base_path` is a worker-side local path used only for file-missing warnings, never for Locations.
- `traktor-nml-utils` (v4.0.0+) is the primary NML parsing library. It uses xsdata-generated dataclasses that model the full NML schema (entries, locations, cues, playlists, etc.). If xsdata write round-tripping proves fragile, fall back to direct `lxml` writes using the same models as reference.
- The sync worker runs on Linux/NixOS; the Traktor import target is Windows-first.
- Path mappings are configurable in design, even if the first deployment uses a fixed mapping.
- The flake exposes a real runtime package (not just a dev shell) built with `buildPythonApplication` and `lib.cleanSource`.
- A flake app output (`nix run .#default`) delegates to the packaged CLI binary.
- `traktor-nml-utils` is packaged as a Nix derivation from PyPI since it is not in nixpkgs.
- A NixOS module (`nixosModules.traktor-m3u-sync`) exposes named `states.<name>` SQLite domains and independently triggerable `jobs.<name>` actions. One importer may rebuild a state; any number of NML, M3U, iTunes, or Engine exports may consume it (imports support NML and M3U only).
- Two shared import/export systemd templates carry the common CLI and oneshot policy; Nix-declared instance drop-ins provide each job's stable unit identity, effective arguments, and validated asynchronous `OnSuccess=` fan-out.
- Every instance runs under the module-wide product-neutral `playlist-sync` identity by default; custom user/group names and supplementary groups are operator-managed, while numeric UID/GID allocation and path-specific sandboxing remain outside the application contract.
- Each generated job gets one TOML file containing its referenced state store and selected format settings. An optional job-level `configFile` uses externally managed TOML instead.
- Orchestration policy (timers, path triggers, consumer hooks, and Engine DJ offline coordination) is intentionally excluded from the base module — downstream consumers attach it through standard NixOS mechanisms.
- rekordbox XML export writes rekordbox's published "XML file format for playlists sharing" (`DJ_PLAYLISTS` 1.0.0): a collection of tracks keyed by integer TrackID with `Location` rendered from `[rekordbox].location_base` exactly like iTunes, and the stored folder tree under the `ROOT` node. `[rekordbox]` shares `[itunes]`'s shape and the shared `--output-file`/`--location-base`/`--check-base-path` flags apply to the selected format. The store-mediated XML carries no analysis. The separate `usb rekordbox-xml` command writes an enriched XML from Engine’s closed library and USB playlist selection for a native rekordbox reference export.
- Generated M3U, iTunes and rekordbox targets are published atomically via a stdlib same-directory temporary file plus `os.replace`; a failed write leaves the prior target intact and removes the temporary file. NML keeps its backup/restore model instead.
- `export --dry-run` rehearses every export format by running the real exporter against isolated temporary targets (temp dir, temp XML, temp copy of the collection); there is no import dry run and dry runs never touch the configured target or store.
- Engine DJ export uses direct stdlib `sqlite3` against one existing Engine 5.0 media-drive `m.db` (schema 3.0.2 only). It matches store paths to `Track` rows already present in that database. When `[engine].check_base_path` can see the file, it inserts each unknown track as an unanalyzed `Track` row without an explicit id, so Engine's triggers assign its origin and performance data and Engine analyzes it on its next start. Because Engine's tag and artwork import never runs for externally inserted rows, the row carries the tag columns Engine's import would read (via `mutagen`), and embedded art is linked through the `AlbumArt` row keyed by the SHA-1 of the embedded picture. Any thumbnail missing from `<Engine Library>/Artwork/<base64url(hash)>.jpg` is rendered (256-pixel fit, JPEG) and written before the database is published, since Engine never renders a thumbnail for an `AlbumArt` row it did not create. It never creates a database, replays Engine DDL, or modifies existing Engine tracks, analysis, artwork, or tags; `libdjinterop` and endjine remain reference implementations, not runtime dependencies.
- Engine analysis status is part of the adapter: `engine-analysis` reads the managed subtree read-only and reports whether each track's `isAnalyzed` flag and beat grid are saved (observed on Engine 5.0 to land while Engine is still open, not only on exit). The flake also ships `engine-analysis-guest`, a Windows logon task that starts and normally closes Engine on a file-based request protocol. VM lifecycle, dialog handling and triggers stay downstream.
- DJ performance data (key, beat grid, main cue, hot cues, saved loops) has its own versioned, serializable model in `model/performance.py`, separate from the playlist model and store. It is the contract between performance adapters and the unit of player-edit diffs, not an authoritative store: Engine is the source of truth, and exporters carry Engine's saved grid unchanged. The Engine codec decodes and re-encodes `PerformanceData` blobs byte for byte.
- USB exports (`usb build`/`push`/`review`) bypass the playlist store. `[usb]` selects a closed Engine source, playlist tree, output root and formats; `[usb.device]` configures one SFTP endpoint. Engine USB is a native clone retaining IDs, origins and analysis, with a stable device UUID and content-addressed media. Each format publishes a staged tree and manifest, and delivery tracks each format separately for the stick's marker UUID. It sends assets before databases and rejects unknown databases unless the exact Engine database was reviewed. Pioneer's database switch is recoverable on retry, not atomic as a set. Stick discovery and triggers stay downstream; the module exposes a build unit and a push template per `services.traktor-m3u-sync.usb.<name>` profile.
- Pioneer USB output is written by `pioneer-usb`, a Rust helper on rbxport's crates (`rbl-export`, `rbl-anlz`, `rbl-analysis`) pinned to one upstream revision. It reads a snapshot and writes `export.pdb`, `exportExt.pdb`, `exportLibrary.db`, the analysis files and `Contents/`, with Engine's grid, key and cues unchanged; only waveforms are computed, from the audio, and cached per file. rbxport's own incremental export into a persistent directory keeps unchanged audio and analysis.
- Engine ownership is one configured managed subtree (default `Playlist Sync`), deleted and rebuilt idempotently while unrelated Engine playlists stay untouched. v1 targets only the M: media database; L: main-library mirroring, Engine import, and metadata enrichment remain deferred.
- Engine publication runs only while Engine DJ is closed (the VM may remain running) and is distinct from generated-file publish: a mode-preserving same-directory staged copy is mutated in one transaction, validated, backed up to an adjacent retained single-generation `.playlist-sync.bak`, then atomically replaced via `os.replace`; the replacement inode is owned by the worker identity and follows the directory's group policy, and a post-publication validation failure restores the backup.
- `--fail-on-warning` is an opt-in strict mode for import and export: completed-with-warnings exits `2`, errors stay `1`, and the default (flag absent) keeps warnings at `0`.
- The TOML config contract remains the primary CLI interface; the module's Nix-level options map 1:1 to the same TOML structure.
- The repository license is GPL-3.0-or-later.

## NML format: key structures and path handling

Traktor `collection.nml` is a single XML file. Key structural elements for this project:

**Track location** (three-part path):
```xml
<LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="track.mp3"/>
```
- `VOLUME`: drive letter on Windows (`C:`), volume name on macOS (`Macintosh HD`)
- `DIR`: path using `/:` as separator (Traktor's convention, not standard)
- `FILE`: filename
- Reconstructed path on Windows: `C:\Music\House\track.mp3`
- On macOS: `/Volumes/Macintosh HD/Music/House/track.mp3`

**PRIMARYKEY** (alternate path reference):
```xml
<PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track.mp3"/>
```

**Playlist tree**:
```xml
<PLAYLISTS>
  <NODE TYPE="FOLDER" NAME="$ROOT">
    <SUBNODES>
      <NODE TYPE="PLAYLIST" NAME="My Playlist">
        <PLAYLIST TYPE="LIST" ENTRIES="N">...</PLAYLIST>
      </NODE>
      <NODE TYPE="SMARTLIST" NAME="Smart Crates">...</NODE>
    </SUBNODES>
  </NODE>
</PLAYLISTS>
```

**NML safety constraints**:
- Always keep a backup before modifying; Traktor overwrites on exit
- Traktor renames malformed files to `collection_backup_invalid.nml` and starts fresh — this loses everything
- Traktor uses explicit close tags (`<X></X>`, never `<X/>`), 6-decimal floats, and specific XML declaration
- Do not modify while Traktor is running (it holds a write lock)
- Smartlist write support is poorly tested; avoid for now

## Risks to account for later

- Traktor-compatible NML write safety (round-trip fidelity testing needed)
- Path mapping edge cases across environments (Windows drive letters, macOS volumes, `/:` separators)
- Exact playlist tree reconstruction semantics (SUBNODES nesting, FOLDER vs PLAYLIST)
- Missing-track behavior and reporting fidelity
- Keeping root docs and OpenSpec artifacts in sync
