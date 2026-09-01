# Architecture

## Purpose

`traktor-m3u-sync` is a Nix-first Python CLI worker that bridges playlist libraries through a multi-format pipeline. Traktor `collection.nml` and UTF-8 `.m3u8` are import/export modalities; iTunes XML is an export modality; Engine DJ remains deferred.

## Architecture: store-mediated multi-format bridge

The system is a hub-and-spoke bridge. The hub is a format-neutral playlist model plus a local SQLite store; each format is a pair of adapter modules that only translates between its native representation and the hub. Import and export are independent processes that communicate through the store.

1. **Model (`model/`)** — frozen playlist/track dataclasses with identity normalization: a track's identity is its casefolded POSIX library-relative path, with an artist+title fallback only for entries that have no resolvable path (ambiguous fallbacks warn; unresolvable entries are stored flagged, never dropped).
2. **Store (`store/`)** — SQLite (stdlib `sqlite3`) cache at `[store].path`. Rebuildable, disposable state: every import performs a wholesale wipe-and-rebuild in one transaction. A `meta` table carries the schema version; mismatches fail fast with a re-import directive — there are no migrations.
3. **Format adapters (`formats/<fmt>/`)** — per format, an `Importer` (`read(source) -> ImportResult`) and/or `Exporter` (`write(playlists, target) -> ExportResult`) plus format-internal helpers. Adapters emit shared structured warning/result types and hold no cross-format knowledge.
4. **Paths (`paths/`)** — each path-bearing format owns its mapping: `[nml].library_root` and `[m3u].library_root` translate native forms (Traktor `VOLUME`/`DIR`/`FILE`/`PRIMARYKEY`, M3U relative/absolute) to and from library-relative identity space, and a pure `file:` URI mapping renders consumer-facing iTunes Locations from `[itunes].location_base` independent of the worker filesystem.
5. **Services (`services/`)** — thin orchestration only: resolve config, select the format's adapter, run it, rebuild or read the store, summarize. Format selection is a registry lookup.
6. **CLI (`cli.py`)** — `import --format nml|m3u` (source → store) and `export --format nml|m3u|itunes` (store → target). Export reads only the store and fails fast when it is empty or uninitialized.

Adding a format means one adapter package and any required path mapping or config section; no other format needs format-specific orchestration. iTunes XML export is implemented; Engine DJ is the next deferred modality.

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
- TOML is the configuration format, with format-based sections (`[store]`, `[nml]`, `[m3u]`, `[itunes]`) and per-command CLI overrides. There is no global `[library]` table (retired by `format-path-mappings`).
- Library roots belong to their format: `[nml].library_root` and `[m3u].library_root`, each required only when a command selects that format; unselected adapters impose no configuration.
- iTunes Locations and Music Folder render from `[itunes].location_base`, a complete consumer-facing absolute `file:` URI (empty, `localhost`, and UNC authorities supported; UTF-8 percent-encoding preserving `/` and drive colons). Optional `[itunes].check_base_path` is a worker-side local path used only for file-missing warnings, never for Locations.
- `traktor-nml-utils` (v4.0.0+) is the primary NML parsing library. It uses xsdata-generated dataclasses that model the full NML schema (entries, locations, cues, playlists, etc.). If xsdata write round-tripping proves fragile, fall back to direct `lxml` writes using the same models as reference.
- The sync worker runs on Linux/NixOS; the Traktor import target is Windows-first.
- Path mappings are configurable in design, even if the first deployment uses a fixed mapping.
- The flake exposes a real runtime package (not just a dev shell) built with `buildPythonApplication` and `lib.cleanSource`.
- A flake app output (`nix run .#default`) delegates to the packaged CLI binary.
- `traktor-nml-utils` is packaged as a Nix derivation from PyPI since it is not in nixpkgs.
- A NixOS module (`nixosModules.traktor-m3u-sync`) exposes separate format-generic oneshot `export` and `import` service surfaces with an overridable `package` option; export supports NML, M3U, and iTunes while import supports NML and M3U.
- The module runs both oneshots under a product-neutral `playlist-sync` system identity by default; custom user/group names and supplementary groups are operator-managed, while numeric UID/GID allocation and path-specific sandboxing remain outside the application contract.
- Declarative TOML config is rendered into the Nix store; services invoke the CLI with `--config` pointing at the store path.
- An optional `configFile` override lets operators provide an externally managed TOML file instead of rendering from Nix options.
- Orchestration policy (timers, path triggers, Syncthing hooks) is intentionally excluded from the base module — downstream consumers attach scheduling via standard NixOS mechanisms.
- Generated M3U and iTunes targets are published atomically via a stdlib same-directory temporary file plus `os.replace`; a failed write leaves the prior target intact and removes the temporary file. NML keeps its backup/restore model instead.
- `export --dry-run` rehearses every export format by running the real exporter against isolated temporary targets (temp dir, temp XML, temp copy of the collection); there is no import dry run and dry runs never touch the configured target or store.
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
