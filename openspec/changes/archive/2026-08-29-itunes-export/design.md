# Design: itunes-export

## Context

The `playlist-store` change established the internal model, SQLite store, and `Importer`/`Exporter` adapter contracts; `export --format <fmt>` renders store state only. This change adds the iTunes XML exporter as the first new adapter on that frozen contract. Format ground truth comes from the research brief (real Apple fixtures + DJ-oriented generators): plist structure, `file://` URL encoding, folder representation, and consumer tolerance are documented there and in project memory.

## Goals / Non-Goals

**Goals:**

- One adapter package (`formats/itunes/`) rendering store state to an iTunes-compatible XML plist via stdlib `plistlib`.
- Idempotent exports: stable Track IDs / Persistent IDs derived deterministically from track identity.
- Folder hierarchy mirroring via iTunes folder playlists.
- Structured warnings consistent with the shared adapter contract (including missing-local-file warnings).

**Non-Goals:**

- iTunes XML import (reverse direction) — deferred.
- Smart playlist support — never emitted.
- Engine DJ direct DB adapter — separate future change.
- Local file validation as a blocker — existence is checked and reported, never fatal.
- Writing Music.app-managed fields (Play Count, Rating, Distinguished Kind, Master).

## Decisions

### D1: plistlib with default XML format

`plistlib.dumps(root, fmt=plistlib.FMT_XML)` — emits the Apple DTD header, handles all escaping (never hand-escape), sorts keys alphabetically (fine for consumers). No third-party plist library.

### D2: Document shape — minimal-plus

Top level: `Major Version` (1), `Minor Version` (1), `Application Version` (package name), `Date` (tz-aware UTC now), `Music Folder` (`base_path` as URI), `Library Persistent ID` (stable 16-hex derived from a fixed seed), `Tracks`, `Playlists`. Community-verified minimal DJ imports work with less, but headers, `Music Folder`, and `Library Persistent ID` are cheap and maximize consumer compatibility.

Per track: `Track ID` (int), `Name`, `Artist`, `Album` (when known), `Total Time` (ms, from stored seconds), `Track Type` = `"File"`, `Location`, `Persistent ID` (16-hex). Per playlist: `Name`, `Playlist ID` (int), `Playlist Persistent ID` (16-hex), `Playlist Items` (array of `Track ID` int refs), and folder flags where applicable. Omit everything else.

### D3: ID generation — deterministic from identity

Track IDs: stable integers assigned by sorted identity order (rebuild-safe across runs with identical store state). Persistent IDs: uppercase 16-hex derived from a hash of a lossless canonical serialization of identity or ordered folder-path segments plus name. Do not delimiter-join segments; use a length-preserving serialization. Resolve any truncated-hash collision deterministically so IDs remain unique in one document. No random IDs; repeated exports of unchanged state produce byte-identical output except `Date`.

### D4: Track ID typing follows Apple's convention

`Tracks` outer dict keys are `str(track_id)`; inner `Track ID` values and `Playlist Items` refs are `int`. `plistlib` writes this Apple-shaped form natively.

### D5: Locations — absolute `file://` URIs from base_path

`[itunes].base_path` SHALL be absolute; configuration rejects a relative value before export. Location = `(base_path / library_relative_path).as_uri()`; `Path.as_uri()` handles percent-encoding (spaces, `#`, non-ASCII). Tracks whose identity is unresolved (no library-relative path) are skipped with structured warnings rather than emitted with fabricated Locations — referential integrity means skipped tracks must also be omitted from playlist items, which the store join makes mechanical. `Music Folder` is `base_path.as_uri()` with trailing slash; it is informational only.

### D6: Folder mirroring

Stored folder paths (POSIX segments) map to nested iTunes folder playlists: one folder entry per path segment with `Folder = true`, `All Items = true`, stable Persistent ID (derived from the segment path), and children carrying `Parent Persistent ID`. Root-level playlists omit `Parent Persistent ID`. Never emit `Distinguished Kind` or `Master` on user playlists.

### D7: Existence check — warn, don't block

After building Locations, the exporter checks each against the local filesystem (only when the check is meaningful — i.e. paths are absolute and the library may be mounted). Missing files produce structured warnings counted in the summary; the export itself always completes. Configurable off via the existing warning machinery if needed later.

### D8: Command and config surface

`export --format itunes` registered in the CLI format registry; services need no changes beyond registration (pure store-only render). `[itunes]` section: `output_file` (target XML path, required), `base_path` (library root for Locations, required), plus standard CLI overrides. Config validation follows the existing per-command required-field pattern.

### D9: NixOS export-only module support

The NixOS module keeps the existing separate import/export oneshots. Its export format enum adds `itunes`, its import format enum remains `nml|m3u`, and generated configuration gains an `[itunes]` section with `output_file` and absolute `base_path`. Module assertions and the flake module-eval fixture validate the selected export format's fields. Scheduling and import→export chaining remain downstream systemd policy.

## Risks / Trade-offs

- [Engine DJ's exact minimal tolerance is undocumented] → we emit the conservative minimal-plus shape; live validation against Engine DJ is an explicit follow-up before homelab deployment.
- [Sorted-identity Track IDs change if store content changes] → acceptable: IDs need only be internally consistent within one file; stability across unchanged state is what prevents churn.
- [Unresolved tracks silently dropped from playlists] → per warning policy: skipped with structured warnings and summary counts, consistent with skip-and-warn behavior everywhere else.
- [`Date` makes exports non-byte-identical] → harmless; IDs (the dedup-relevant part) remain stable.

## Migration Plan

Purely additive adapter: implement behind the existing registry, add config section + tests, update docs. No data migration; the store schema is untouched.

## Open Questions

None — hierarchy mirroring and existence-check policy were resolved with the user; format details are pinned by the research brief.
