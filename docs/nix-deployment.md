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
| `library.traktor_root` | string | — | Traktor library root (Windows path format) |
| `library.m3u_root` | string | — | M3U library root |
| `store.path` | null/string | `null` | SQLite store path; null keeps the tool default |
| `nml.collection_path` | null/string | `null` | Path to `collection.nml`; required for `nml` format services |
| `nml.sandbox_name` | string | `"Imported Playlists"` | Sandbox folder name in Traktor |
| `m3u.output_dir` | null/string | `null` | Directory for generated `.m3u8` files; required for `export.format = "m3u"` |
| `m3u.import_dir` | null/string | `null` | Directory containing M3U files to import; required for `import.format = "m3u"` |
| `itunes.output_file` | null/string | `null` | iTunes Music Library XML output path; required for `export.format = "itunes"` |
| `itunes.base_path` | null/string | `null` | Absolute library root for iTunes track Locations; required for `export.format = "itunes"` |
| `export.enable` | bool | `false` | Enable the export oneshot service |
| `export.format` | null/`"nml"`/`"m3u"`/`"itunes"` | `null` | Export target format, passed as `--format` (required when enabled) |
| `export.extraArgs` | list of strings | `[]` | Extra CLI arguments appended after `--format` and `--config` |
| `import.enable` | bool | `false` | Enable the import oneshot service |
| `import.format` | null/`"nml"`/`"m3u"` | `null` | Import source format, passed as `--format` (required when enabled) |
| `import.extraArgs` | list of strings | `[]` | Extra CLI arguments appended after `--format` and `--config` |

The rendered `[library]`, `[store]`, `[nml]`, `[m3u]`, and `[itunes]` tables match the
TOML schema the CLI loader requires; the chosen service `format` decides
which fields the module asserts on.
`itunes` is export-only; `import.format` accepts only `nml` and `m3u`.

The module creates two systemd oneshot services:

- `traktor-m3u-sync-export.service`
- `traktor-m3u-sync-import.service`

Both have `wantedBy = []` by default — they are never triggered automatically.

## Config file override

When `configFile` is set, the module uses the external TOML file directly
instead of generating one from Nix options. In that mode:

- `library.*`, `store.*`, `nml.*`, `m3u.*`, and `itunes.*` Nix options are not rendered
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
