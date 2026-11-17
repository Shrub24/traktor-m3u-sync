# Engine USB spike

After playlist sync and analysis finish, keep Engine closed and do not run another sync while staging the export:

```sh
python3 spikes/engine-usb/export.py '/path/to/Engine Library' /path/to/new-usb-tree
```

The output directory must not exist; its parent must exist and have room for the copied audio. By default this includes every playlist and the union of their tracks, not unreferenced tracks. Use `--root 'Playlist Sync'` to stage only that top-level tree. Each run uses the latest database and assets. It does not update an existing stick or preserve edits made on one.

The staged tree preserves native playlist ordering, source track origins and analysis blobs. Audio goes under `Engine Library/Music/<track-id>/` to avoid collisions on case-insensitive USB filesystems. The database gets its own UUID and RGB overviews are filed under that UUID. No personal profile, play-history database, auxiliary cache database or Sync Manager pack state is copied. Whether the SC6000 needs any of those is part of the trial.

## SC6000 acceptance

Use an empty spare drive formatted for the SC6000. Copy `Engine Library` to the **root** of that drive; do not merge it into a library containing player edits. Safely eject the drive. On the SC6000, check that the playlist tree opens in order; load an older track and a newly added track; check playback, artwork, overview, key and grid alignment. If the library has a deliberate cue or loop, check that too. A SQLite integrity pass is not a hardware pass.

Keep Engine as the analysis source. For the later cross-format path, share an Engine reader and canonical track identity, playlist and performance-data types between exporters where they actually need translation. Same-format transfers can preserve native blobs without a decode/re-encode cycle. Importing player edits is a separate operation that should match on origin and compare against what was exported before applying anything.
