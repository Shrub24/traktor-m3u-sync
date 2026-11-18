# Engine USB spike

After playlist sync and analysis finish, keep Engine closed and do not run another sync while staging the export:

```sh
python3 spikes/engine-usb/export.py '/path/to/Engine Library' /path/to/new-usb-tree
```

The output directory must not exist; its parent must exist and have room for the copied audio. By default this includes every playlist and the union of their tracks, not unreferenced tracks. Use `--root 'Playlist Sync'` to stage only that top-level tree. Each run uses the latest database and assets. It does not update an existing stick or preserve edits made on one.

The staged tree preserves native playlist ordering, source track origins and analysis blobs. Audio goes under `Engine Library/Music/<track-id>/` to avoid collisions on case-insensitive USB filesystems. The database gets its own UUID and RGB overviews are filed under that UUID. No personal profile, play-history database, auxiliary cache database or Sync Manager pack state is copied. Whether the SC6000 needs any of those is part of the trial.

## Manual delivery through Android

Use a spare stick with no existing Engine database for the first install. Create a random UUID with `uuidgen` and put it on one line in `.playlist-sync-stick` at the USB root. In sshd4a, authorize a dedicated home-forge public key and start the SSH server on the private network. Use the OpenSSH backend for this trial and configure the SFTP session to start at the USB root: the delivery command resolves the marker and all export paths relative to that directory. Verify the phone's SSH host key out of band and add it to a dedicated known-hosts file (`[host]:port` for a nonstandard port). Keep Engine and any other stick writer closed during delivery.

From home-forge, run from the repo root:

```sh
nix shell --impure --expr 'let p = (builtins.getFlake "nixpkgs").legacyPackages.${builtins.currentSystem}; in p.python3.withPackages (ps: [ ps.paramiko ])' -c \
  python3 spikes/engine-usb/push.py /path/to/staged-tree PHONE_HOST STICK_UUID \
  --port SSH_PORT --user SSH_USER --key ~/.ssh/dj-usb \
  --known-hosts ~/.ssh/dj-usb-known-hosts --state ~/.local/state/dj-usb
```

This previews the changes. Add `--apply` to write to the stick. Keep the staged tree unchanged while the command runs, and keep the private state directory: it holds both database backups and the per-stick manifests needed to recognize completed exports. Preview may save a local database backup but does not write to the USB.

The host hashes the staged tree locally. It reads the stick marker and database, not the whole media tree. File mtimes do not matter. Unchanged media is trusted from the last recognized install; this is not a full scan for externally removed or corrupted files. On retry, a new asset already at its final path is read back to confirm it matches. Newly uploaded media is checked for length; the uploaded database is hashed back before publication. A fresh Engine device UUID creates fresh RGB paths, so new builds can transfer the overview files even when audio is unchanged.

Refresh requires SFTP `posix-rename` with overwrite support. The command tests it on disposable files in the database directory first and has no delete-and-rename fallback. This passed against standalone OpenSSH; verify it on sshd4a with the actual USB attached. A database with player edits is backed up and refused, as is a changed asset at a path still referenced by the old export. No media is deleted. The delivery code is separate from Engine export; the manual entry point only supports Engine today. A Pioneer adapter must define how to publish its multiple library files safely. sshd4a's rsync can be evaluated later for asset transfers; it does not replace manifest comparison, database backup, or database-last publication.

On a spare stick, apply an initial export, preview it again (expect zero transfers), then apply an export with one more track. Test a dropped connection before publication and retry. Wait for delivery to complete, stop sshd4a, and eject the USB in Android before unplugging. A stopped SFTP server is not an eject.

## SC6000 acceptance

Use an empty spare drive formatted for the SC6000. Copy `Engine Library` to the **root** of that drive; do not merge it into a library containing player edits. Safely eject the drive. On the SC6000, check that the playlist tree opens in order; load an older track and a newly added track; check playback, artwork, overview, key and grid alignment. If the library has a deliberate cue or loop, check that too. A SQLite integrity pass is not a hardware pass.

Keep Engine as the analysis source. For the later cross-format path, share an Engine reader and canonical track identity, playlist and performance-data types between exporters where they actually need translation. Same-format transfers can preserve native blobs without a decode/re-encode cycle. Importing player edits is a separate operation that should match on origin and compare against what was exported before applying anything.
