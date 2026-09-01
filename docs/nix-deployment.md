# Nix Deployment Reference

Concise reference for building, deploying, and operating `traktor-m3u-sync`
via Nix.

## Flake outputs

| Output | Description |
|---|---|
| `packages.<system>.traktor-m3u-sync` | Runtime package (Python 3.14, hatchling build) |
| `packages.<system>.traktor-nml-utils` | Vendored dependency (not in nixpkgs) |
| `packages.<system>.default` | Alias for `traktor-m3u-sync` |
| `apps.<system>.default` | `nix run` entry point |
| `devShells.<system>.default` | Dev shell with git, just, lefthook, python314, pyright, ruff, treefmt, uv |
| `checks.<system>.formatting` | treefmt formatting check |
| `checks.<system>.module-eval` | NixOS module evaluation smoke test |
| `nixosModules.traktor-m3u-sync` | NixOS module |
| `nixosModules.default` | Alias for the module |

Supported systems: `x86_64-linux`, `aarch64-linux`.

## NixOS module options

All options live under `services.traktor-m3u-sync.*`.

| Option | Type | Default | Description |
|---|---|---|---|
| `enable` | bool | `false` | Enable the traktor-m3u-sync services |
| `package` | package | flake package | Override the runtime package |
| `configFile` | null/path | `null` | External TOML config (overrides generated config) |
| `user` | null/string | `"playlist-sync"` | Service account; custom user/group names must be supplied together and already exist; `null` runs as root |
| `group` | null/string | `"playlist-sync"` | Primary service group; use the matching default or a matching custom identity |
| `supplementaryGroups` | list of strings | `[]` | Existing shared groups added to both service processes |
| `store.path` | null/string | `null` | SQLite store path; null keeps the tool default |
| `nml.library_root` | null/string | `null` | NML library root; required for `nml` format services |
| `nml.collection_path` | null/string | `null` | Path to `collection.nml`; required for `nml` format services |
| `nml.sandbox_name` | string | `"Imported Playlists"` | Sandbox folder name in Traktor |
| `m3u.library_root` | null/string | `null` | M3U library root; required for `m3u` format services |
| `m3u.output_dir` | null/string | `null` | Directory for generated `.m3u8` files; required for `export.format = "m3u"` |
| `m3u.import_dir` | null/string | `null` | Directory containing M3U files to import; required for `import.format = "m3u"` |
| `itunes.output_file` | null/string | `null` | iTunes Music Library XML output path; required for `export.format = "itunes"` |
| `itunes.location_base` | null/string | `null` | Complete absolute `file:` URI for iTunes track Locations; required for `export.format = "itunes"` |
| `itunes.check_base_path` | null/string | `null` | Optional local worker path for iTunes missing-file warnings |
| `export.enable` | bool | `false` | Enable the export oneshot service |
| `export.format` | null/`"nml"`/`"m3u"`/`"itunes"` | `null` | Export target format, passed as `--format` (required when enabled) |
| `export.extraArgs` | list of strings | `[]` | Extra CLI arguments appended after `--format` and `--config` |
| `import.enable` | bool | `false` | Enable the import oneshot service |
| `import.format` | null/`"nml"`/`"m3u"` | `null` | Import source format, passed as `--format` (required when enabled) |
| `import.extraArgs` | list of strings | `[]` | Extra CLI arguments appended after `--format` and `--config` |

The rendered `[store]` table and selected format tables match the TOML schema
the CLI loader requires. `nml.library_root` is required only for `nml`
services, `m3u.library_root` only for `m3u` services, and iTunes requires
`output_file` plus an absolute `file:` `location_base` only for iTunes export.
The URI may use an empty, `localhost`, or hostname (UNC) authority; whitespace,
malformed percent escapes, queries, and fragments are rejected during evaluation.
`check_base_path` is optional and is used only for local worker warnings.
`itunes` is export-only; `import.format` accepts only `nml` and `m3u`.

The module creates the product-neutral `playlist-sync` system user and group by default, then runs both oneshots under that identity. NixOS allocates the numeric UID/GID and assigns its standard `nologin` shell. Keep both defaults together; custom `user` and `group` names must also be supplied together and are treated as operator-managed. Set both to `null` only as an explicit root escape hatch. Generated configuration requires an explicit `store.path` when running non-root because the CLI's home-relative fallback is not writable by the system account.

Before starting a service, grant its identity access to every configured path. The import service needs read access to `m3u.import_dir` and write access to the store parent; exports need write access to their target. Prefer directory ownership or `supplementaryGroups = [ "media" ]`; don't replace only the default primary group. The base module deliberately does not hard-code homelab paths or `ReadOnlyPaths=`/`ReadWritePaths=` sandbox policy.

The module creates two systemd oneshot services:

- `traktor-m3u-sync-export.service`
- `traktor-m3u-sync-import.service`

Both have `wantedBy = []` by default — they are never triggered automatically. `Restart = "no"`; any uncaught CLI/configuration/filesystem error therefore returns a non-zero unit result instead of being hidden or retried.

### Service identity and permissions

Default generated units contain:

```ini
User=playlist-sync
Group=playlist-sync
```

The module creates that product-neutral system account only when both defaults are kept. To use an existing host account, set both options together:

```nix
services.traktor-m3u-sync = {
  user = "media-worker";
  group = "media";
};
```

For shared access without replacing the default primary identity:

```nix
services.traktor-m3u-sync.supplementaryGroups = [ "media" ];
```

Grant the resulting identity filesystem access before starting the units. For example, an M3U-to-iTunes deployment needs:

- read/execute access to `m3u.import_dir` and `itunes.check_base_path`;
- write/execute access to the parent of `store.path` and `itunes.output_file`;
- any parent-directory traversal permissions required to reach those paths.

The module does not change ownership of arbitrary runtime paths. Use declarative directory ownership, group permissions, or ACLs in the host configuration. `ReadOnlyPaths=` and `ReadWritePaths=` are optional systemd sandbox restrictions, not permission grants; configure them downstream using the host's real paths.

Use root only as an explicit escape hatch:

```nix
services.traktor-m3u-sync = {
  user = null;
  group = null;
};
```

## Config file override

When `configFile` is set, the module uses the external TOML file directly
instead of generating one from Nix options. In that mode:

- `store.*`, `nml.*`, `m3u.*`, and `itunes.*` Nix options are not rendered
  into any config file; the generated-config assertions are skipped
- The runtime workflow values come entirely from the external file
- `export.format` / `import.format` are still required (passed as `--format`)
- Use this for externally managed configs (e.g. Syncthing-deployed files)

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

## Downstream orchestration

Services are oneshot units with no bundled timers or triggers. Attach
scheduling in your own NixOS config.

The module embeds no operational policy: `--dry-run` (export-only) and
`--fail-on-warning` (exit `2` on completed-with-warnings) are plain CLI flags.
Pass them through the appropriate public `extraArgs` option:

```nix
services.traktor-m3u-sync.export.extraArgs = [ "--fail-on-warning" ];
```

With `--fail-on-warning`, exit status `2` fails the oneshot unit by design, so
`Restart=no` plus downstream unit dependencies/alerting can act on
completed-with-warnings runs. Status `1` still means a real failure and
status `0` means success (with or without warnings when the flag is absent).

### Export timer (daily at 03:00)

```nix
systemd.timers.traktor-m3u-sync-export = {
  wantedBy = [ "timers.target" ];
  timerConfig = {
    OnCalendar = "03:00";
    Persistent = true;
  };
};
```

### Import timer (every 15 minutes)

```nix
systemd.timers.traktor-m3u-sync-import = {
  wantedBy = [ "timers.target" ];
  timerConfig = {
    OnCalendar = "*:0/15";
    Persistent = true;
  };
};
```

### Syncthing folder watch

For Syncthing-managed setups, use a path unit that triggers import when
the playlist directory changes:

```nix
systemd.paths.traktor-m3u-sync-import = {
  wantedBy = [ "paths.target" ];
  pathConfig = {
    PathModified = "/mnt/playlists";
    Unit = "traktor-m3u-sync-import.service";
  };
};
```

## traktor-nml-utils packaging

[`traktor-nml-utils`](https://github.com/wolkenarchitekt/traktor-nml-utils)
is not available in nixpkgs. The flake packages it from PyPI as a vendored
derivation (`nix/packages/traktor-nml-utils.nix`):

- Source: PyPI sdist (currently v4.1.0)
- Build dependency: `setuptools`
- Runtime dependencies: `typer`, `xsdata`
- Tests: disabled (`doCheck = false`) — upstream has no pytest suite
- License: GPL-3.0-only

The package is exposed as `packages.<system>.traktor-nml-utils` and
consumed automatically by the main `traktor-m3u-sync` package. No manual
intervention needed unless you need to override the version.
