# Architecture

## Purpose

`traktor-m3u-sync` is intended to become a Nix-first Python CLI worker for synchronizing Traktor playlist state with UTF-8 `.m3u8` playlists.

The long-term target is bidirectional synchronization between:

- Traktor `collection.nml`
- exported/imported `.m3u8` playlists

Navidrome-facing automation may consume the generated playlists later, but that integration is outside this repository's first bootstrap phase.

## High-level architecture direction

The planned architecture is a small CLI-oriented application with clear subsystem boundaries:

1. **Configuration layer**
   - path mappings
   - sync mode and sandbox settings
   - filesystem and report output paths

2. **NML domain layer**
   - load and inspect Traktor playlist/tree state
   - later support controlled sandbox import mutation

3. **M3U domain layer**
   - read and write UTF-8 `.m3u8` playlists
   - preserve playlist ordering and exported directory hierarchy

4. **Path translation layer**
   - normalize Traktor Windows paths
   - derive relative-path-based matching for import
   - support configurable path mappings

5. **Sync orchestration layer**
   - export workflow: NML → M3U
   - import workflow: M3U → NML sandbox rebuild
   - conflict/reporting behavior at workflow boundaries

6. **Reporting layer**
   - import/export summaries
   - unresolved track warnings
   - durable sync reports/logs where needed

## Confirmed architectural decisions

- Python 3.14 is preferred.
- Development and packaging are Nix-first.
- CLI-first design; no GUI is planned.
- Import behavior will begin with a sandbox overwrite model rather than fine-grained merge logic.
- Track matching for early import work is based on filename plus relative path.
- Missing import matches should be skipped and reported.
- Exported playlists use UTF-8 `.m3u8`.
- TOML is the configuration format.
- `traktor-nml-utils` (v4.0.0+) is the primary NML parsing library. It uses xsdata-generated dataclasses that model the full NML schema (entries, locations, cues, playlists, etc.). If xsdata write round-tripping proves fragile, fall back to direct `lxml` writes using the same models as reference.
- The sync worker runs on Linux/NixOS; the Traktor import target is Windows-first.
- Path mappings are configurable in design, even if the first deployment uses a fixed mapping.

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
